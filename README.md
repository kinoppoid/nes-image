# nes-image

BMPファイルをNES（ファミコン）用スライドショーROMに変換するプロジェクト。
複数の画像をファミコン実機またはエミュレータで表示し、コントローラで切り替えられる。

## 機能

- **自動画像変換**: BMPを256×160px（32×20タイル）に自動リサイズ・変換
- **NESパレット最適化**: k-meansクラスタリング（CIE L\*a\*b\* 彩度加重）で各画像に最適な4パレットを選択
- **色レスキュー**: 緑・肌色が失われないよう自動補正
- **Atkinsonディザリング**: タイル単位のディザリングで圧縮効率を向上
- **タイル重複排除**: 256スロットに自動割り当て（超過時は自動縮小）
- **LZE圧縮**: CHRデータ・ネームテーブルをLZSSベースで圧縮（約30〜40%削減）
- **プレビュー出力**: NES実機出力と一致する `_preview.png` を生成
- **NROM-256対応**: PRG-ROM 32KBに収まる枚数まで対応（目安10枚）

## ビルド環境

```bash
sudo apt install cc65
pip install Pillow numpy scikit-learn
```

- `cc65` / `ca65` / `ld65` — NES向けCコンパイラ・アセンブラ・リンカ
- `python3` — 画像変換スクリプト（tools/make_chr.py）
- [lze.py](https://github.com/kinoppoid/88-image/blob/main/lze.py) — LZEエンコーダ（`../88image/lze.py` として配置）

## 使い方

```bash
make                        # ../src-images/*.bmp を変換してROMを生成
make SRC_DIR=../src2        # 入力ディレクトリを指定
make MAX_IMAGES=10          # 変換枚数の上限を指定
make GREEN_RESCUE=0         # 緑レスキューを無効化
make clean                  # 生成物を削除
```

出力: `image.nes`（エミュレータ・実機カートリッジで使用可能なiNES形式ROM）

## 操作

| ボタン | 動作 |
|---|---|
| A または → | 次の画像へ（最後→最初に戻る） |
| B または ← | 前の画像へ（最初→最後に戻る） |

## ファイル構成

```
nes-image/
├── Makefile
├── nes.cfg             # ld65リンカ設定
├── src/
│   └── main.c          # メインプログラム（C）
├── asm/
│   ├── crt0.s          # スタートアップ
│   ├── lzedec.s        # LZEデコーダ（6502アセンブリ）
│   ├── ppu_utils.s     # PPUユーティリティ
│   ├── chr.s           # CHRデータ定義
│   ├── chr_lze.s       # LZE圧縮CHRデータ
│   ├── zeropage.s      # ゼロページ変数
│   ├── attributes.inc  # アトリビュートデータ（生成）
│   ├── nametable.inc   # ネームテーブルデータ（生成）
│   ├── palettes.inc    # パレットデータ（生成）
│   └── img_data.s      # 画像データまとめ（生成）
└── tools/
    └── make_chr.py     # 画像変換・ROMデータ生成スクリプト
```

## ハードウェア仕様

| 項目 | 内容 |
|---|---|
| マッパー | 0（NROM-256） |
| PRG-ROM | 32KB |
| CHR | CHR-RAM 8KB（実行時書き込み） |
| ミラーリング | 水平 |

実機カートリッジには PRG-ROM（27C256相当）と SRAM（6264相当）が必要。

詳細は [REQUIREMENTS.md](REQUIREMENTS.md) を参照。
