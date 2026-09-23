# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2017-2020 Yousong Zhou <yszhou4tech@gmail.com>
# Copyright (C) 2021-2023 ImmortalWrt.org

include $(TOPDIR)/rules.mk

PKG_NAME:=shadowsocks-rust
PKG_VERSION:=1.25.0
# PKG_RELEASE bump 记录:
#   2: 100-disable-broken-crypto-backend.patch（shadowsocks-crypto 0.8.0
#      的 ring/aws-lc 分支有发布 bug——ring 分支缺 Aes128Gcm 类型定义，
#      aws-lc 分支同样 E0432，唯一可编译路径是纯 Rust fallback）
PKG_RELEASE:=2

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/shadowsocks/shadowsocks-rust/tar.gz/v$(PKG_VERSION)?
PKG_HASH:=477a525e9b11d4c90ded6629552548d00a32675ec6f6f18ee45c98447e54b5f3

PKG_MAINTAINER:=Tianling Shen <cnsztl@immortalwrt.org>
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE

PKG_BUILD_DEPENDS:=rust/host
PKG_BUILD_PARALLEL:=1

RUST_PKG_FEATURES:=local-redir
# 加密后端为 ring（见 patches/100-use-ring-crypto-backend.patch），上游
# Cargo.lock 只含 aws-lc-rs/aws-lc-sys 无 ring-compat，--locked 会因依赖
# 树变化失败，禁用锁定让 cargo 自行解析。
RUST_PKG_LOCKED:=0

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-package.mk

define Package/shadowsocks-rust/Default
  define Package/shadowsocks-rust-$(1)
    SECTION:=net
    CATEGORY:=Network
    SUBMENU:=Web Servers/Proxies
    TITLE:=shadowsocks-rust $(1)
    URL:=https://github.com/shadowsocks/shadowsocks-rust
    DEPENDS:=$$(RUST_ARCH_DEPENDS)
  endef

  define Package/shadowsocks-rust-$(1)/install
	$$(INSTALL_DIR) $$(1)/usr/bin
	$$(INSTALL_BIN) $$(PKG_INSTALL_DIR)/bin/$(1) $$(1)/usr/bin/
  endef
endef

SHADOWSOCKS_COMPONENTS:=sslocal ssmanager ssserver ssurl ssservice
define shadowsocks-rust/templates
  $(foreach component,$(SHADOWSOCKS_COMPONENTS),
    $(call Package/shadowsocks-rust/Default,$(component))
  )
endef
$(eval $(call shadowsocks-rust/templates))

$(foreach component,$(SHADOWSOCKS_COMPONENTS), \
  $(eval $(call BuildPackage,shadowsocks-rust-$(component))) \
)
