from dataclasses import dataclass
from typing import List, Dict, Any
import logging

@dataclass()
class PatchConfig:
    manifest_version: int
    interface: str
    bug: str
    filename: str
    context_above: str
    context_below: str
    unpatched: str
    patches: List[str]

    def __post_init__(self):
        assert self.manifest_version==3

def load(data: Dict[str, Any]) -> PatchConfig:
    mv = data.get('manifest_version', None)

    if mv==2:
        logging.debug('migrating manifest v2 to v3')

        data['interface'] = 'defects4j'
        data['bug'] = f'{data["project"]}-{data["version"]}'
        del data['project']
        del data['version']

        data['manifest_version'] = 3
        mv = 3

    if mv!=3:
        raise RuntimeError(f'invalid manifest version: {mv}')

    return PatchConfig(**data)