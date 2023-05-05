import pathlib
import time
from typing import Tuple
from xml.etree import ElementTree as ET
import io
from shlex import quote
import shutil
from threading import Lock

from utils import run_cmd
from patcher import BasePatcher, VERBOSE

cache_lock = Lock()
known_not_maven_projs = set()

GROUPID_FIXUP = {
    'Lang': 'org.apache.commons',
    'Time': 'org.joda.time',
}

def parse_maven_time(line: str) -> float:
    '''
    Source at https://github.com/apache/maven/blob/master/maven-embedder/src/main/java/org/apache/maven/cli/CLIReportingUtils.java#L168
    Examples at https://github.com/apache/maven/blob/master/maven-embedder/src/test/java/org/apache/maven/cli/CLIReportingUtilsTest.java#L30
    '''
    if '(' in line: # `XXXs (Wall Clock)`
        line = line.partition('(')[0]

    line = line.strip()
    d, h, m, s = 0, 0, 0, 0

    if ' d ' in line: # `1 d 00:00 h`
        d, _, line = line.partition(' d ')

    line, sfx = line.split(' ')
    if sfx=='h':
        h, m = line.split(':')
    elif sfx=='min':
        m, s = line.split(':')
    elif sfx=='s':
        s = line

    d = int(d)
    h = int(h)
    m = int(m)
    s = float(s)

    return d*86400 + h*3600 + m*60 + s

class UniAprPatcher(BasePatcher):
    COMPILE_TIMEOUT_SEC = 120
    DOWNLOAD_TIMEOUT_SEC = 300
    RUN_TEST_TIMEOUT_SEC_EACH = 600
    RUN_TEST_TIMEOUT_SEC_MAX = 3600

    # https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
    MAVEN_SP_SRC = 'src/main/java'
    MAVEN_SP_TEST = 'src/test/java'
    MAVEN_TP_SRC = 'target/classes'
    MAVEN_TP_TEST = 'target/test-classes'

    def __init__(self, jsonpath):
        super().__init__(jsonpath, checkout=False)

        with cache_lock:
            if (self.config.project, self.config.version) in known_not_maven_projs:
                raise RuntimeError('pom not found (from cache)')

        if not self.workpath.exists():
            self.checkout()

        self.cp_compile = self.prop('cp.compile')
        self.cp_test = self.prop('cp.test')  # "Classpath to compile and run the developer-written tests"
        self.tp_src = self.prop('dir.bin.classes')
        self.tp_test = self.prop('dir.bin.tests')
        self.sp_src = self.prop('dir.src.classes')
        self.sp_test = self.prop('dir.src.tests')

        self.tests_trigger = self.prop('tests.trigger').split('\n')

        self.poolpath = self.workpath/'patches-pool'
        self.poolpath.mkdir(exist_ok=True)

        assert self.config.filename.startswith(self.sp_src)
        assert not self.sp_src.endswith('/')
        self.rel_filename = self.config.filename[(len(self.sp_src)+1):]  # org/apache/commons/lang3/time/FastDateFormat.java

        assert self.rel_filename.endswith('.java')
        self.rel_binfilename = self.rel_filename[:-len('.java')]+'.class'  # org/apache/commons/lang3/time/FastDateFormat.class

    def compile_unpatched(self):
        succ, t = self.compile(self.COMPILE_TIMEOUT_SEC)
        assert succ, 'cannot compile unpatched'

        srcpath = self.workpath/self.tp_src/self.rel_binfilename
        assert srcpath.exists(), 'bin file does not exist'

        shutil.move(srcpath, self.poolpath/'_original_binfile')

    def copy_classes(self):
        if self.tp_src!=self.MAVEN_TP_SRC:
            print(' - move tp_src from', self.tp_src)
            shutil.copytree(self.workpath/self.tp_src, self.workpath/self.MAVEN_TP_SRC, dirs_exist_ok=True)

        if self.tp_test!=self.MAVEN_TP_TEST:
            print(' - move tp_test from', self.tp_test)
            shutil.copytree(self.workpath/self.tp_test, self.workpath/self.MAVEN_TP_TEST, dirs_exist_ok=True)

    def patch_pom(self):
        pom_path = pathlib.Path('../uniapr/pom_files')/f'{self.config.project.title()}-{self.config.version}-pom.xml'
        if pom_path.exists():
            print(' - copy pom')
            shutil.copy(pom_path, self.workpath/'pom.xml')

        pom_path = self.workpath/'pom.xml'
        if not pom_path.exists():
            with cache_lock:
                known_not_maven_projs.add((self.config.project, self.config.version))
            raise RuntimeError('pom not found')

        with pom_path.open('r') as f:
            content = f.read()

        document = ET.ElementTree()
        document.parse(io.StringIO(content))

        namespace = document.getroot().tag.rpartition('project')[0] # `{http://maven.apache.org/POM/4.0.0}`

        # add uniapr plugin

        plugins_elem = document.find('./%sbuild/%splugins'%(namespace, namespace))
        assert plugins_elem is not None, 'plugins elem not found in pom'

        print(' - written failingTests:', len(self.tests_trigger))

        new_elem = ET.fromstring(f'''
            <plugin>
                <groupId>org.uniapr</groupId>
                <artifactId>uniapr-plugin</artifactId>
                <version>1.0-SNAPSHOT</version>
                <configuration>
                    <resetJVM>true</resetJVM>
                    <failingTests>
                        {" ".join(map(lambda t: "<failingTest>"+t+"</failingTest>", self.tests_trigger))}
                    </failingTests>
                </configuration>
            </plugin>
        ''')
        plugins_elem.append(new_elem)

        # change junit version

        dep_elems = document.findall('./%sdependencies/%sdependency'%(namespace, namespace))
        for dep_elem in dep_elems:
            group_id = dep_elem.find('./%sgroupId'%namespace)
            artifact_id = dep_elem.find('./%sartifactId'%namespace)
            if group_id is not None and artifact_id is not None and group_id.text.strip()=='junit' and artifact_id.text.strip()=='junit':
                version = dep_elem.find('./%sversion'%namespace)
                if version is not None:
                    print(' - junit version', version.text)
                    vss = [int(x) for x in version.text.strip().split('.')]
                    if vss[0]<4 or (vss[0]==4 and vss[1]<12):
                        version.text = '4.12'
                        print('  -> changed to', version.text)

        # change groupId
        # https://pitest.org/quickstart/maven/ says:
        # `pitest assumes that your classes live in a package matching your projects group id`

        group_id = document.find('./%sgroupId'%namespace)
        if group_id is not None and '.' not in group_id.text.strip():
            print(' - group id', group_id.text)
            group_id.text = GROUPID_FIXUP[self.config.project.title()]
            print('  -> changed to', group_id.text)

        # https://stackoverflow.com/questions/18338807/cannot-write-xml-file-with-default-namespace
        ET.register_namespace('', namespace[1:-1])

        with (self.workpath/'pom.xml').open('wb') as f:
            document.write(f)

    def _collect_patch(self, patch, pidx):
        with (self.workpath/self.config.filename).open('w') as f:
            f.write(self.config.context_above + patch + self.config.context_below)

        lang_level = self.get_language_level()
        javac_cmdline = (
            f'javac'
            f' -cp {quote(self.cp_compile)}'
            f' -d {quote(str((self.workpath/self.tp_src).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f' -source 1.{lang_level} -target 1.{lang_level}'
            f' {quote(str((self.workpath/self.config.filename).resolve()))}'
        )

        errcode, time_sec, stdout, stderr = run_cmd(javac_cmdline, timeout_sec=self.COMPILE_TIMEOUT_SEC, cwd=self.workpath)

        if errcode:
            print('PATCH #%d CANNOT COMPILE'%(pidx+1), errcode)
            return False

        else:
            print('patch #%d can compile'%(pidx+1))

            srcpath = self.workpath/self.tp_src/self.rel_binfilename
            assert srcpath.exists()

            destpath = self.poolpath/str(pidx+1)/self.rel_binfilename
            destpath.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(srcpath, destpath)

            return True


    def collect_all_patches(self):
        patchcnt = 0
        succlist = ''
        for ind, patch in enumerate(self.config.patches):
            if self._collect_patch(patch, ind):
                succlist += '?'
                patchcnt += 1
            else:
                succlist += 'C'

        # move original bytecode back
        shutil.move(self.poolpath/'_original_binfile', self.workpath/self.tp_src/self.rel_binfilename)

        return patchcnt, succlist

    def fixup_if_needed(self):
        if self.config.project.lower()=='lang' and self.config.version in [51, 55, 57, 59]:
            # package name `enum`
            assert (self.workpath/'src/test/org/apache/commons/lang/enums').is_dir()
            assert (self.workpath/'src/java/org/apache/commons/lang/enums').is_dir()
            shutil.rmtree(self.workpath/'src/test/org/apache/commons/lang/enum')
            shutil.rmtree(self.workpath/'src/java/org/apache/commons/lang/enum')
            for p in self.workpath.glob('**/*.java'):
                with p.open('rb') as f:
                    src = f.read()
                src = src\
                    .replace(b'org.apache.commons.lang.enum.', b'org.apache.commons.lang.enums.')\
                    .replace(b'org.apache.commons.lang.enum;', b'org.apache.commons.lang.enums;')
                with p.open('wb') as f:
                    f.write(src)

    def exec_uniapr(self, patchcnt: int, succlist: str) -> Tuple[str, list]:
        timeout = min(self.RUN_TEST_TIMEOUT_SEC_MAX, self.RUN_TEST_TIMEOUT_SEC_EACH*patchcnt)

        # `-Dhttps.protocols=TLSv1.2` mentioned in UniAPR README, don't know why
        # `-Dstyle.color=never` to remove annoying ANSI color codes
        errcode, time_sec, stdout, stderr = run_cmd('mvn org.uniapr:uniapr-plugin:validate -Dhttps.protocols=TLSv1.2 -Dstyle.color=never', timeout, self.workpath)

        if errcode or 'Patch Validator is DONE!' not in stdout:
            print('EXEC UNIAPR FAILED', errcode)
            print('stderr <<< %s >>>'%stderr)
            print('stdout <<< %s >>>'%stdout)
            1/0

        if 'java.lang.NoSuchMethodError: org.junit.Assert.assertEquals(' in stdout:
            raise RuntimeError('KNOWN ISSUE: junit version erroor')

        if 'RUNNING: ' not in stdout:
            raise RuntimeError('KNOWN ISSUE: no tests found')

        # parse stdout

        print(stdout)

        chunks, _, summary = stdout.rpartition('Patch Validator is DONE!')
        chunks = chunks.split('>>Validating patchID: ')
        assert len(chunks)==patchcnt+1

        succcnt = 0
        succlist = list(succlist)
        assert succlist.count('?')==patchcnt
        for chunk in chunks[1:]:
            patchid = int(chunk.partition('\n')[0])
            if 'WARNING: Running test cases is terminated.' in chunk:
                succlist[patchid-1] = 'F'
            else:
                succlist[patchid-1] = 's'
                succcnt += 1
        succlist = ''.join(succlist)

        real_succcnt = int(summary.partition('# of plausible patches: ')[2].partition('\n')[0])
        uniapr_reported_time_ms = int(summary.partition('***VALIDATION-TOOK: ')[2].partition('\n')[0])
        maven_reported_time_s = parse_maven_time(summary.partition('[INFO] Total time: ')[2].partition('\n')[0])
        assert succcnt==real_succcnt
        return succlist, [uniapr_reported_time_ms/1000, maven_reported_time_s]

    def mvn_populate_cache(self):
        print('= populate cache')
        errcode, time_sec, stdout, stderr = run_cmd('mvn dependency:go-offline', self.DOWNLOAD_TIMEOUT_SEC, self.workpath)

        if errcode:
            print('MVN POPULATE CACHE FAILED', errcode)
            print('stderr <<< %s >>>'%stderr)
            print('stdout <<< %s >>>'%stdout)
            # ignore errors because sometimes uniapr continues to work even this fails
            #1/0

    def main(self): # patchcnt, t_compile, t_run, succlist, reported_time_s
        print('= compile unpatched')
        self.fixup_if_needed()
        self.compile_unpatched()

        self.patch_pom()
        self.mvn_populate_cache()

        print('= collect patch')
        t1 = time.time()

        patchcnt, succlist = self.collect_all_patches()
        print(' got', patchcnt, 'patches')

        # do this after patches are compiled because patches may invoke other new classes
        self.copy_classes()

        t2 = time.time()
        telemetry = None

        if patchcnt:
            print('= exec uniapr')
            succlist, telemetry = self.exec_uniapr(patchcnt, succlist)
        t3 = time.time()

        return patchcnt, t2-t1, t3-t2, succlist, telemetry