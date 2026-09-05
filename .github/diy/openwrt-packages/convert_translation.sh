#!/bin/bash

set -euo pipefail
shopt -s nullglob

for po_dir in luci-*/po; do
	if [[ -d "$po_dir/zh-cn" && ! -e "$po_dir/zh_Hans" && ! -L "$po_dir/zh_Hans" ]]; then
		ln -s zh-cn "$po_dir/zh_Hans"
	elif [[ -d "$po_dir/zh_Hans" && ! -e "$po_dir/zh-cn" && ! -L "$po_dir/zh-cn" ]]; then
		ln -s zh_Hans "$po_dir/zh-cn"
	fi
done
