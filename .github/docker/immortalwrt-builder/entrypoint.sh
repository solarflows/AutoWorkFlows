#!/bin/bash
set -e

# 应用环境变量
USERNAME=${USERNAME:-builduser}
PASSWORD=${PASSWORD:-password}
TTYD_PORT=${TTYD_PORT:-7681}
SSH_PORT=${SSH_PORT:-2222}

# 配置SSH
sed -i "s/#Port 22/Port ${SSH_PORT}/" /etc/ssh/sshd_config
echo "PermitRootLogin no" >> /etc/ssh/sshd_config
service ssh start

# 启动ttyd服务
su ${USERNAME} -c "ttyd -p ${TTYD_PORT} bash" &

# 保持容器运行
tail -f /dev/null
