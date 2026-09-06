
#!/bin/bash

set -euo pipefail

find . -mindepth 2 -type d \( -name .git -o -name .svn -o -name .github \) -prune -exec rm -rf -- {} +
find . -mindepth 2 -type f \( -name .gitattributes -o -name .gitignore \) -delete

rm -rf -- create_acl_for_luci.err
rm -rf -- create_acl_for_luci.ok
rm -rf -- create_acl_for_luci.warn

exit 0
