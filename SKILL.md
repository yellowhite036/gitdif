---
name: diff-commit-message
description: Generate a Chinese (Traditional, zh-Hant) git commit message by diffing "before" and "after" versions of uploaded files (e.g. app_js.before/app_js.after, index_html.before/index_html.after, styles_css.before/styles_css.after). Trigger this whenever the user uploads paired *.before / *.after files (or similarly named before/after variants of the same file) and asks for a "commit message", "commit log", "改動說明", "diff 摘要", or similar — even if they don't explicitly say "diff". Also trigger when the user says things like "給我 commit message" after uploading files, or "參考這個格式" referring to a previously generated commit message in this conversation. Do NOT trigger for normal code-writing or code-review requests that don't involve before/after file pairs.
---

# Diff → Commit Message (繁體中文)

從使用者上傳的一組 `*.before` / `*.after` 檔案自動 diff，產生繁體中文（zh-Hant）的 git commit message，格式與語氣需符合本 skill 定義的規範。**只需要輸出 commit message 本身**，不要額外提供程式碼、不要重寫檔案內容，除非使用者另外要求。

## 何時觸發

- 使用者上傳成對的 `xxx.before` / `xxx.after` 檔案（副檔名任意，例如 `app_js.before`／`app_js.after`、`index_html.before`／`index_html.after`、`styles_css.before`／`styles_css.after`），並要求 commit message、commit log、改動說明、diff 摘要等。
- 使用者只上傳其中幾個檔案對（不一定三個都有），依實際上傳的檔案產生對應章節即可，沒上傳的檔案不要提及。
- 使用者說「參考這個格式」時，代表沿用本 skill 定義的格式（見下方「輸出格式」）。

## 執行步驟

1. **找出所有的 before/after 檔案配對**。常見命名規則是 `{basename}.before` 對應 `{basename}.after`（例如 `app_js.before` ↔ `app_js.after`）。忽略沒有成對出現的檔案。
2. **對每一組檔案做 diff，並忽略換行符號（CRLF/LF）差異**，否則整個檔案會因為換行符不同而顯示成全部改動。務必使用類似指令：
   ```bash
   diff --strip-trailing-cr -u <file>.before <file>.after
   ```
   如果檔案內容看起來整份都變了（幾乎每一行都是 `-`/`+`），先檢查是否為縮排/換行符造成的雜訊，必要時可用 `diff -w`（忽略空白）或手動比對邏輯區塊，找出**真正有意義的變更**，忽略純格式化（縮排從 4 空白改 2 空白、單純換行符轉換）。
3. **理解每個變更的語意**，不要只複製 diff 的 `+`/`-` 行。要判斷：
   - 新增/移除/重新命名了哪些函式、變數、CSS class、HTML 元素/id
   - 邏輯行為改變了什麼（例如：驗證規則、狀態機、資料結構、事件綁定）
   - 是否為資料模型調整（例如陣列改關聯表、欄位新增/移除）
   - 是否為單純格式調整（縮排、換行符轉換），若是，只需一行帶過，不要展開細節
4. **判斷 commit type**（用於開頭前綴）：
   - `Feat:` 新增功能／新增欄位／新增 UI 元素
   - `Fix:` 修正錯誤行為
   - `Refactor:` 重構既有邏輯、資料結構調整但外部行為大致不變
   - `Style:` 純樣式/格式調整（少見，通常會和其他變更合併，此時前綴用主要異動的 type）
   - 若同時有多種性質的變更，選擇影響最大的當前綴，其餘變更照樣列在對應檔案段落下
5. **依照下方「輸出格式」組合成 commit message**，直接輸出成一則可複製的純文字內容（用 code block 包住，方便使用者複製），不要加多餘的前後說明文字。

## 輸出格式

```
<Type>: <一句話總結本次變更，繁體中文，涵蓋主要目的>

<檔名1，例如 app.js>

* <變更項目1，具體到函式/變數/id層級>
* <變更項目2>
* ...

<檔名2，例如 index.html>

* <變更項目1>
* ...

<檔名3，例如 styles.css>
（若無變更則整段省略，不要寫「無變更」）

* <變更項目1>
* ...
```

格式規則：

- 標題行格式固定為 `<Type>: <摘要>`，例如 `Feat: 新增物料管理 CRUD 功能與導覽權限控管`、`Refactor: 產品 BOM 改為關聯表結構，工單建立移除庫存/模具約束檢查並新增產品庫存累加`。
- 摘要控制在一行內講完，允許用逗號或頓號連接多個重點，但不要超過約 40–50 字。
- 檔名區塊標題用還原後的實際檔名（`app_js.before` → `app.js`，`index_html.before` → `index.html`，`styles_css.before` → `styles.css`），不要用底線版檔名。
- 沒有變更的檔案（diff 完全相同）**整段省略**，不要列出來也不要寫「無變更」。
- 每個項目用 `*` 條列，一行一項，具體點出函式名稱（加反引號或原樣呈現）、id、class、欄位名稱等技術細節，讓熟悉 codebase 的人一看就懂改了什麼。
- 純格式/縮排/換行符調整只需一句話帶過（例如「整體縮排格式調整（4 空白改為 2 空白），結構未變」），不要逐行列舉。
- 全程使用繁體中文（台灣用語），程式相關的專有名詞（function、id、class、enum 等）可保留英文原文或加反引號標示。
- 不要在 commit message 內加入表情符號、簽名檔、`Co-authored-by` 等額外資訊，除非使用者要求。
- 最終輸出用單一 code block 包住整段 commit message，方便使用者一鍵複製；code block 前後不要加額外的分析文字或客套話（例如不要說「以下是 commit message：」），除非變更內容有需要特別提醒使用者注意的地方（例如發現某個變更可能是 bug），才在 code block 之後補一句簡短提醒。

## 範例

輸入：使用者上傳 `app_js.before` / `app_js.after`，diff 顯示新增了 `renderPreview()` 內對 `#submitWorkOrderBtn` 的 disabled 狀態控制，以及 `index_html.before`/`after` 中該按鈕新增了 `id="submitWorkOrderBtn"`。

輸出：

```
Feat: 模具非閒置時停用工單送出按鈕

app.js

* renderPreview() 新增按鈕狀態控制邏輯：當所選組合無對應產品，或綁定模具狀態非 Idle 時，將 #submitWorkOrderBtn 設為 disabled，並調整透明度與游標樣式提示不可點擊；模具為 Idle 時恢復可點擊狀態

index.html

* 工單送出按鈕新增 id="submitWorkOrderBtn"，供 app.js 控制其啟用/停用狀態
```
