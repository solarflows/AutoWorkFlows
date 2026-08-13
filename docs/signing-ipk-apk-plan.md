# 签名机制分流（IPK usign vs APK ECDSA）

> 状态: **已实施**（2026-08-13）
> 结论: 包格式（APK/IPK）与签名方式不再由 target 静态配置，改为构建时从实际配置自动探测 `CONFIG_USE_APK`。单 secret 存私钥，公钥由 CI 派生，无需第二个公钥 secret。

## 一、两平台签名机制差异

| 维度 | mt798x（IPK / opkg） | qualcommax（APK / apk） |
|:--|:--|:--|
| 包格式 | IPK（opkg） | APK（apk） |
| 签名算法 | **usign**（Ed25519） | openssl **ECDSA prime256v1**（或 RSA） |
| 私钥文件名 | `key-build`（104 字节 seckey 结构，**非 PEM**） | `private-key.pem`（PEM） |
| 公钥文件名 | `key-build.pub`（42 字节 pubkey 结构） | `public-key.pem`（PEM） |
| 构建系统自动生成 | ❌ 无生成规则，须手动 | ✅ `openssl ecparam -genkey` |
| secret | `USIGN_KEY` | `APK_BUILD_KEY` |

## 二、最终设计（核心决策）

1. **版本探测替代静态字段**：`targets.json` 不再有 `apk_signing` 字段。全量构建读 `.config` 的 `CONFIG_USE_APK=y`；SDK 增量读 SDK `Config-build.in` 的 `config USE_APK`（`convert-config.pl` 把 `.config` 转成 Kconfig 格式）。分支升级到 snapshot/APK 无需改配置。
2. **单 secret 派生公钥**：不设 `USIGN_PUB_KEY`。usign 公钥从私钥派生（见 §三）；APK 公钥用 `openssl ec -pubout` 派生。
3. **sign_mode 四态**：`apk` / `usign` / `random`（密钥缺失或无效时构建系统用随机密钥）/ `none`。写入 `build-info.json`（`signing_mode` + `signing_key_fingerprint`）与 release notes。
4. **单个 `Setup Signing Key` 步骤**：放在 `make defconfig` 之后（密钥在 `package/index` 阶段才生成，非 defconfig），按探测结果 if/else 注入对应密钥。

## 三、usign 密钥格式（关键实现细节）

`openwrt/usign` `main.c` 定义的私钥结构（104 字节）：

```c
struct seckey {            // 104 字节
	char pkalg[2];         // "Ed"
	char kdfalg[2];        // "BK"
	uint32_t kdfrounds;    // 0
	uint8_t salt[16];
	uint8_t checksum[8];
	uint8_t fingerprint[8]; // offset 32
	uint8_t seckey[64];     // seed[32] || pubkey[32]；pubkey 在 offset 72
};
```

- `key-build` 文件 = `untrusted comment: private key <fp>` 一行 + `base64(104 字节)` 一行
- `key-build.pub` 文件 = `untrusted comment: public key <fp>` 一行 + `base64("Ed" + fingerprint[8] + pubkey[32])`（42 字节）
- CI 派生逻辑（无 usign 工具依赖）：`base64 -d key-build` → 校验 104 字节 → 指纹取 `dd skip=32 count=8`、公钥取 `dd skip=72 count=32`

## 四、代码佐证（源码证据）

### 1. usign 密钥生成（`openwrt/usign` `main.c`，`usign -G`）

```c
fread(skey.seckey, EDSIGN_SECRET_KEY_SIZE /*32*/, 1, f); // /dev/urandom 随机 seed
ed25519_prepare(skey.seckey);                            // clamp
edsign_sec_to_pub(skey.seckey + 32, skey.seckey);        // 公钥派生到 seed 后 32 字节
b64_encode(&skey, sizeof(skey) /*104*/, buf, ...);       // base64 整个结构
```

### 2. OpenWrt 21.02 签 Packages 索引（`package/Makefile` `index`）

```make
# rules.mk: BUILD_KEY=$(TOPDIR)/key-build
ifdef CONFIG_SIGNED_PACKAGES
	$(STAGING_DIR_HOST)/bin/usign -S -m Packages -s $(BUILD_KEY)
endif
```

### 3. APK 密钥生成（main 分支 `package/Makefile`）

```make
# rules.mk: BUILD_KEY_APK_SEC=$(TOPDIR)/private-key.pem  BUILD_KEY_APK_PUB=$(TOPDIR)/public-key.pem
$(BUILD_KEY_APK_SEC):
	$(STAGING_DIR_HOST)/bin/openssl ecparam -name prime256v1 -genkey -noout -out $(BUILD_KEY_APK_SEC)
$(BUILD_KEY_APK_PUB): $(BUILD_KEY_APK_SEC)
	$(STAGING_DIR_HOST)/bin/openssl ec -in $(BUILD_KEY_APK_SEC) -pubout > $(BUILD_KEY_APK_PUB)
```

### 4. APK 签索引（main 分支 `package/Makefile` `index`）

```make
apk mkndx --root $(TOPDIR) --keys-dir $(TOPDIR) --allow-untrusted \
    $(if $(CONFIG_SIGNED_PACKAGES),--sign $(BUILD_KEY_APK_SEC),) --output packages.adb *.apk
```

> 结论：`usign` 用 Ed25519 + 自定义 104 字节结构，**不能用 openssl 生成**；APK 用 openssl ECDSA prime256v1，构建系统会自动生成。

## 五、密钥生成与导入

### 生成（需在 OpenWrt 环境 / SDK 工具链）

```bash
./staging_dir/host/bin/usign -G -s key-build -p key-build.pub        # usign 密钥对
openssl ecparam -name prime256v1 -genkey -noout -out private-key.pem  # APK 私钥
openssl ec -in private-key.pem -pubout -out public-key.pem            # APK 公钥
```

### 导入 GitHub secret（用 `<` 重定向，内容不进 shell 历史）

```bash
gh secret set USIGN_KEY     --repo solarflows/AutoWorkFlows < key-build
gh secret set APK_BUILD_KEY --repo solarflows/AutoWorkFlows < private-key.pem
```

- `USIGN_KEY` 存 `key-build` 完整文件内容（含 `untrusted comment` 头 + base64 行）
- `APK_BUILD_KEY` 存 PEM 全文
- **私钥本体必须离线备份**（GitHub secret 是单点，丢失后签名不可再续），本地明文可删

## 六、实施清单

- [x] `compile-firmware.yml`：`Apply Configuration` 探测 `CONFIG_USE_APK` → `Setup Signing Key`（单步骤，按 use_apk 分流）
- [x] `compile-packages.yml`：`Setup Signing Key` 探测 `Config-build.in` → SDK Build / IB 三处分流
- [x] `firmware-build-unified.yml`：三处 `secrets:` 块透传 `USIGN_KEY`
- [x] `targets.json` / `README.md` / `openwrt-config.instructions.md`：移除 `apk_signing`，改自动探测说明
- [x] 公钥发布：APK → `solarflows-apk-public.pem`，usign → `solarflows-usign-public.pub`
- [x] release notes：4 分支签名状态（apk / usign / random / none）
- [ ] 用户添加 secret：`USIGN_KEY` + `APK_BUILD_KEY`（见 §五）

## 七、注意

1. **usign 私钥校验**：按 104 字节 seckey 结构校验（非 64 字节裸 seed）；失败时警告 + 降级 `random` 继续构建
2. **密钥生成时机**：APK `private-key.pem` / usign `key-build` 均在 `package/index` 签名阶段生成，故注入只需在编译前（`make defconfig` 之后）即可
3. **`CONFIG_USE_APK` 是可靠分流开关**：`CONFIG_SIGNED_PACKAGES` 仅表示"启用签名"（两平台都有），不能区分格式
4. **SDK 增量需重新注入**：SDK tarball 不含密钥，`compile-packages` 在 SDK/IB 根目录重新注入 `key-build` 或 `private-key.pem`
