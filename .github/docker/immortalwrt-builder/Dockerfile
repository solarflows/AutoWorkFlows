# 使用Ubuntu LTS基础镜像
FROM ubuntu:22.04

# 设置可配置参数
ARG USERNAME=builder
ARG PASSWORD=password
ARG TTYD_PORT=7681
ARG SSH_PORT=2222

# 安装基础环境
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    sudo locales tzdata \
    && rm -rf /var/lib/apt/lists/*

# 配置时区/语言环境
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && locale-gen en_US.UTF-8

# 安装编译依赖（分阶段安装避免层过大）
RUN apt update -y && \
    apt install -y \
    autoconf automake binutils bison build-essential \
    bzip2 ccache clang cmake cpio curl device-tree-compiler \
    flex gawk gettext gcc-multilib g++-multilib git gnutls-dev \
    gperf lib32gcc-s1 libc6-dev-i386 libelf-dev libgmp3-dev \
    libltdl-dev libmpc-dev libmpfr-dev libncurses-dev libpython3-dev \
    libreadline-dev libssl-dev libtool libz-dev lld llvm ninja-build \
    patch pkgconf python3 python3-pip python3-ply python3-docutils \
    python3-pyelftools re2c rsync squashfs-tools unzip wget zlib1g-dev zstd \
    && rm -rf /var/lib/apt/lists/*

# 创建普通用户并设置密码
RUN useradd -m -s /bin/bash ${USERNAME} \
    && echo "${USERNAME}:${PASSWORD}" | chpasswd \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# 安装额外工具
RUN apt-get update && apt-get install -y \
    ttyd openssh-server \
    && rm -rf /var/lib/apt/lists/*

# 配置工作目录和权限
RUN mkdir /workdir && chown ${USERNAME}:${USERNAME} /workdir
VOLUME /workdir
WORKDIR /workdir

# 暴露端口配置
EXPOSE ${TTYD_PORT} ${SSH_PORT}

# 启动配置
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
