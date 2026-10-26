#!/usr/bin/env bash
# Host prerequisites only. Run with sudo from an interactive terminal.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    echo 'Run: sudo bash scripts/install_host_tools.sh' >&2
    exit 2
fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 26.04 ]] || {
    echo 'This reviewed bootstrap targets the inspected Ubuntu 26.04 host.' >&2
    exit 2
}
# Do not remove/replace an existing container installation.
if command -v docker >/dev/null || command -v nvidia-ctk >/dev/null; then
    echo 'Container tools already exist; inspect their configuration before continuing.' >&2
    exit 2
fi
apt-get update
apt-get install -y --no-install-recommends --no-remove \
    docker.io=29.1.3-0ubuntu4.1 git-lfs=3.7.1-1 \
    vulkan-tools=1.4.341.0+dfsg1-1 util-linux-extra ca-certificates curl gnupg
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey -o "$temp_dir/nvidia.asc"
gpg --batch --dearmor --output "$temp_dir/nvidia.gpg" "$temp_dir/nvidia.asc"
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    -o "$temp_dir/nvidia.list"
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    "$temp_dir/nvidia.list" > "$temp_dir/nvidia-signed.list"
install -m 0644 "$temp_dir/nvidia.gpg" /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
install -m 0644 "$temp_dir/nvidia-signed.list" /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update
toolkit_version=1.20.1-1
apt-get install -y --no-install-recommends --no-remove \
    "nvidia-container-toolkit=$toolkit_version" \
    "nvidia-container-toolkit-base=$toolkit_version" \
    "libnvidia-container-tools=$toolkit_version" \
    "libnvidia-container1=$toolkit_version"
if [[ -f /etc/docker/daemon.json ]]; then
    cp -a /etc/docker/daemon.json "/etc/docker/daemon.json.before-studio-$(date -u +%Y%m%dT%H%M%SZ)"
fi
nvidia-ctk runtime configure --runtime=docker
systemctl enable --now docker
systemctl restart docker
if [[ -n ${SUDO_USER:-} && "$SUDO_USER" != root ]]; then
    usermod -aG docker "$SUDO_USER"
fi
dpkg-query -W docker.io git-lfs vulkan-tools nvidia-container-toolkit \
    nvidia-container-toolkit-base libnvidia-container-tools libnvidia-container1
echo 'Installed prerequisites. New login sessions gain Docker group access.'
