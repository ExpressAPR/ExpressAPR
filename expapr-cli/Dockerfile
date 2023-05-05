FROM ubuntu:22.04
RUN apt update

# set locale to en_US
# copied from https://hub.docker.com/_/ubuntu
RUN apt install -y locales && \
	localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

# install d4j and dependencies
RUN apt install -y openjdk-8-jdk git subversion perl-base cpanminus libdbi-perl
RUN apt install -y build-essential curl unzip
RUN git clone https://github.com/rjust/defects4j /defects4j && \
    cd /defects4j && \
    git checkout v2.0.0
RUN cd /defects4j && \
    cpanm --installdeps . && \
    ./init.sh
ENV PATH $PATH:/defects4j/framework/bin

# install our dependencies
RUN apt install -y python3.10 python3-pip
COPY cli/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# put our code
COPY cli /expapr/cli
COPY expapr-jar /expapr/expapr-jar

WORKDIR /expapr
ENTRYPOINT ["python3", "-m", "cli"]
