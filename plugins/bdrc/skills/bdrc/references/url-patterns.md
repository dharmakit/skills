# BDRC URL Patterns

## 搜索

| 用途 | URL |
|------|-----|
| 目录搜索 | `https://library.bdrc.io/search?q={QUERY}` |
| 全文搜索 | `https://library.bdrc.io/osearch/search?q={QUERY}` |
| 翻页 | 追加 `&page={N}` (每页 20 条) |

## 文献详情

| 用途 | URL |
|------|-----|
| 文献详情页 | `https://library.bdrc.io/show/bdr:{MW_ID}` |
| 图像查看器 | `https://library.bdrc.io/view/bdr:{VOLUME_ID}` |

## PDF 下载

| 用途 | URL |
|------|-----|
| 请求生成 PDF | `https://iiif.bdrc.io/download/pdf/v:bdr:{VOL_ID}::{FROM}-{TO}` |
| 实际 PDF 文件 | `https://iiif.bdrc.io/download/file/pdf/bdr:{VOL_ID}:{FROM}-{TO}` |
| ZIP 下载 | `https://iiif.bdrc.io/download/zip/v:bdr:{VOL_ID}::{FROM}-{TO}` |

## IIIF

| 用途 | URL |
|------|-----|
| 单页图像 | `https://iiif.bdrc.io/bdr:{VOL_ID}::{IMG_ID}.jpg/full/max/0/default.jpg` |
| Manifest | `https://iiifpres.bdrc.io/wvo:bdr:{OUTLINE_ID}::bdr:{VOL_ID}/manifest` |
| Collection | `https://iiifpres.bdrc.io/collection/wio:bdr:{MW_ID}::bdr:{W_ID}` |

## 认证

- Auth0 域名: `bdrc-io.auth0.com`
- Client ID: `i0CoWiN3twEMPCA85f0aD9acuIVIFj0J`
- Token 位置: `localStorage.getItem('access_token')`
- 有效期: 2 小时
- 回调地址: `https://library.bdrc.io/auth/callback`

## 注意

- PDF/ZIP 下载需要 Bearer token（`Authorization: Bearer <token>`）
- 单页 IIIF 图像不需要认证
- **永远不要在 cmux 浏览器中打开 PDF URL**（会导致 surface 卡死）
