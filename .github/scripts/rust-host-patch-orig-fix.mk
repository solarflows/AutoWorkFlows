# fix: keep upstream-shipped *.orig in vendor/ (openwrt/packages#27485)
# scripts/patch-kernel.sh 应用 quilt 补丁后会删除所有 *.orig，但 rust 上游
# tarball 的 vendor/ 自带 Cargo.toml.orig 且计入 cargo 校验清单，删除后
# vendor 校验报 "failed to calculate checksum of ... .orig"。
# 上游修复 (openwrt/packages#27487)：覆盖 Host/Patch，自行应用补丁且不清理 .orig。
# 本文件由 compile-packages.yml 幂等追加到 feeds/packages/lang/rust/Makefile 末尾。
define Host/Patch
	$(if $(HOST_QUILT),rm -rf $(HOST_BUILD_DIR)/patches; mkdir -p $(HOST_BUILD_DIR)/patches)
	$(if $(HOST_QUILT),$(call PatchDir/Quilt,$(HOST_BUILD_DIR),$(HOST_PATCH_DIR),))
	$(if $(HOST_QUILT),touch $(HOST_BUILD_DIR)/.quilt_used)
	$(if $(HOST_QUILT),,$(if $(wildcard $(HOST_PATCH_DIR)/*.patch), \
		$(foreach p,$(sort $(wildcard $(HOST_PATCH_DIR)/*.patch)), \
			echo "Applying patch $(notdir $p)" ; \
			$(PATCH) -f -p1 -d $(HOST_BUILD_DIR) < $p || \
			{ echo "Patch failed! Please fix: $(notdir $p)!" ; exit 1 ; } ; \
		) \
	))
endef
