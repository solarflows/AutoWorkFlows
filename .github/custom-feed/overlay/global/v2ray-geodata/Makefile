# SPDX-License-Identifier: GPL-3.0-only
#
# Copyright (C) 2021-2022 ImmortalWrt.org

include $(TOPDIR)/rules.mk

PKG_NAME:=v2ray-geodata
PKG_RELEASE:=1

PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=Tianling Shen <cnsztl@immortalwrt.org>

include $(INCLUDE_DIR)/package.mk

GEO_VER:=202609182348
GEOIP_FULL_FILE:=geoip.dat.$(GEO_VER)
define Download/geoip-full
  URL:=https://github.com/Loyalsoldier/v2ray-rules-dat/releases/download/$(GEO_VER)/
  URL_FILE:=geoip.dat
  FILE:=$(GEOIP_FULL_FILE)
  HASH:=f3370cf391831bb01e1e662df88596164d136e7d9f81a91c00bae26587e02d72
endef

GEOSITE_FULL_FILE:=geosite.dat.$(GEO_VER)
define Download/geosite-full
  URL:=https://github.com/Loyalsoldier/v2ray-rules-dat/releases/download/$(GEO_VER)/
  URL_FILE:=geosite.dat
  FILE:=$(GEOSITE_FULL_FILE)
  HASH:=db2deea2fb5b1bb33f8c5988c3569f024cedab0b9f3a79ae6a2a1c8384254c1f
endef

GEOIP_LITE_FILE:=geoip-lite.dat.$(GEO_VER)
define Download/geoip-lite
  URL:=https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/
  URL_FILE:=geoip-lite.dat
  FILE:=$(GEOIP_LITE_FILE)
  HASH:=skip
endef

GEOSITE_LITE_FILE:=geosite-lite.dat.$(GEO_VER)
define Download/geosite-lite
  URL:=https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/
  URL_FILE:=geosite-lite.dat
  FILE:=$(GEOSITE_LITE_FILE)
  HASH:=skip
endef

define Package/v2ray-geodata/template
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=IP Addresses and Names
  URL:=https://www.v2fly.org
  PKGARCH:=all
endef

define Package/v2ray-geoip-lite
  $(call Package/v2ray-geodata/template)
  TITLE:=meta-rules-dat GeoIP List for V2Ray
  VERSION:=$(GEO_VER).$(PKG_RELEASE)
  LICENSE:=CC-BY-SA-4.0
  VARIANT:=v2ray-geoip-lite
  PROVIDES:=v2ray-geoip
endef

define Package/v2ray-geosite-lite
  $(call Package/v2ray-geodata/template)
  TITLE:=meta-rules-dat Geosite List for V2Ray
  VERSION:=$(GEO_VER).$(PKG_RELEASE)
  LICENSE:=MIT
  VARIANT:=v2ray-geosite-lite
  PROVIDES:=v2ray-geosite
endef

define Package/v2ray-geoip-full
  $(call Package/v2ray-geodata/template)
  TITLE:=GeoIP List for V2Ray
  VERSION:=$(GEO_VER).$(PKG_RELEASE)
  LICENSE:=CC-BY-SA-4.0
  DEFAULT_VARIANT:=1
  VARIANT:=v2ray-geoip-full
  PROVIDES:=v2ray-geoip
  # CONFLICTS:=v2ray-geoip
endef

define Package/v2ray-geosite-full
  $(call Package/v2ray-geodata/template)
  TITLE:=Geosite List for V2Ray
  VERSION:=$(GEO_VER).$(PKG_RELEASE)
  LICENSE:=MIT
  DEFAULT_VARIANT:=1
  VARIANT:=v2ray-geosite-full
  PROVIDES:=v2ray-geosite
  # CONFLICTS:=v2ray-geosite
endef

define Build/Prepare
	$(call Build/Prepare/Default)
ifneq ($(CONFIG_PACKAGE_v2ray-geoip-lite),)
	$(call Download,geoip-lite)
endif
ifneq ($(CONFIG_PACKAGE_v2ray-geosite-lite),)
	$(call Download,geosite-lite)
endif
ifneq ($(CONFIG_PACKAGE_v2ray-geoip-full),)
	$(call Download,geoip-full)
endif
ifneq ($(CONFIG_PACKAGE_v2ray-geosite-full),)
	$(call Download,geosite-full)
endif
endef

define Build/Compile
endef

define Package/v2ray-geoip-lite/install
	$(INSTALL_DIR) $(1)/usr/share/v2ray
	$(INSTALL_DATA) $(DL_DIR)/$(GEOIP_LITE_FILE) $(1)/usr/share/v2ray/geoip.dat
endef

define Package/v2ray-geosite-lite/install
	$(INSTALL_DIR) $(1)/usr/share/v2ray
	$(INSTALL_DATA) $(DL_DIR)/$(GEOSITE_LITE_FILE) $(1)/usr/share/v2ray/geosite.dat
endef

define Package/v2ray-geoip-full/install
	$(INSTALL_DIR) $(1)/usr/share/v2ray
	$(INSTALL_DATA) $(DL_DIR)/$(GEOIP_FULL_FILE) $(1)/usr/share/v2ray/geoip.dat
endef

define Package/v2ray-geosite-full/install
	$(INSTALL_DIR) $(1)/usr/share/v2ray
	$(INSTALL_DATA) $(DL_DIR)/$(GEOSITE_FULL_FILE) $(1)/usr/share/v2ray/geosite.dat
endef

$(eval $(call BuildPackage,v2ray-geoip-lite))
$(eval $(call BuildPackage,v2ray-geosite-lite))
$(eval $(call BuildPackage,v2ray-geoip-full))
$(eval $(call BuildPackage,v2ray-geosite-full))
