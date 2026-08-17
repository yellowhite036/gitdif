Generate a Chinese (Traditional, zh-Hant) git commit message by diffing "before" and "after" versions of uploaded files (e.g. app_js.before/app_js.after, index_html.before/index_html.after, styles_css.before/styles_css.after). Trigger this whenever the user uploads paired *.before / *.after files (or similarly named before/after variants of the same file) and asks for a "commit message", "commit log", "改動說明", "diff 摘要", or similar — even if they don't explicitly say "diff". Also trigger when the user says things like "給我 commit message" after uploading files, or "參考這個格式" referring to a previously generated commit message in this conversation. Do NOT trigger for normal code-writing or code-review requests that don't involve before/after file pairs.

Diff → Commit Message（繁體中文）

從使用者上傳的一組 *.before / *.after 檔案自動 diff，產生繁體中文（zh-Hant）的 git commit message，格式與語氣需符合本 skill 定義的規範。只需要輸出 commit message 本身，不要額外提供程式碼、不要重寫檔案內容，除非使用者另外要求。

核心原則：commit message 裡的每一句話都必須有 diff 輸出可以佐證，不可以憑檔名、憑常識、或憑「這種改動通常會做什麼」來腦補內容。 下面的執行步驟特別針對這點做了強化，務必照順序執行，不要跳步。

何時觸發
使用者上傳成對的 xxx.before / xxx.after 檔案（副檔名任意，例如 app_js.before／app_js.after、index_html.before／index_html.after、styles_css.before／styles_css.after），並要求 commit message、commit log、改動說明、diff 摘要等。
使用者只上傳其中幾個檔案對（不一定三個都有），依實際上傳的檔案產生對應章節即可，沒上傳的檔案不要提及。
使用者說「參考這個格式」時，代表沿用本 skill 定義的格式（見下方「輸出格式」）。
執行步驟
1. 找出所有的 before/after 檔案配對

常見命名規則是 {basename}.before 對應 {basename}.after（例如 app_js.before ↔ app_js.after）。忽略沒有成對出現的檔案，並在心裡（不用跟使用者說）記下每一對的還原檔名（app_js → app.js）。

若某一組只有 .before 沒有 .after（或反之），視為整份檔案被刪除（或新增），照下方「新增/刪除整份檔案」處理，不要略過不提。

2. 對每一組檔案做完整 diff，並實際讀出全文

務必使用類似指令，且要把輸出完整印出來閱讀，不能只看前幾行或用摘要跳過：

bash
diff --strip-trailing-cr -u <file>.before <file>.after
如果檔案內容看起來整份都變了（幾乎每一行都是 -/+），先用 diff --strip-trailing-cr -uw <file>.before <file>.after（加 -w 忽略空白）重跑一次，確認是不是縮排/換行符造成的雜訊。
如果 -w 之後 diff 幾乎消失，代表是純格式化（縮排從 4 空白改 2 空白、換行符轉換等），照「純格式調整」規則處理（一句話帶過，不展開細節，見下方格式規則）。
如果 -w 之後仍有大量差異，代表格式調整與邏輯調整混在一起：先用 -w 版本的 diff 找出「真正有意義」的變更區塊，再回頭對照沒加 -w 的原始 diff 確認上下文，避免把格式雜訊誤判成邏輯變更、也避免把真正的邏輯變更誤判成格式雜訊。這一步一定要雙向核對：-w 版本只是輔助篩選，不能只看 -w 的結果就下結論——同一行如果縮排跟運算子同時被改了，-w 會把整行濾掉，導致真正的邏輯變更被誤判成純格式調整。
判斷是否為「程式碼搬移」（Code Movement）：如果某段函式/區塊只是換了位置（例如搬到檔案別處、換了宣告順序），diff 逐行比對會顯示成一大段刪除＋一大段幾乎相同的新增，容易誤判成「刪除舊函式＋新增新函式」。遇到這種情況，先比對被刪除區塊與新增區塊的內容是否高度相似；如果相似，應描述為「搬移／重新排列」而不是「刪除＋新增」。
對每一個 hunk（@@ ... @@ 區塊）都要逐一看過，不要只分析 diff 輸出的第一個或前幾個 hunk 就下結論——同一個檔案常常有多處不相關的改動分散在不同位置，漏看會導致 commit message 遺漏變更項目。
3. 逐一 hunk 理解語意，並標記每個判斷的證據

不要只複製 diff 的 +/- 行，也不要單看變數/函式名稱就自行腦補「這應該是要做 XXX」。針對每個有意義的 hunk，问自己：

新增/移除/重新命名了哪些函式、變數、CSS class、HTML 元素/id？（這些名稱必須是 diff 輸出裡逐字出現的，不可以自己換句話說改寫成看起來更專業的名字）
邏輯行為改變了什麼（例如：驗證規則、狀態機、資料結構、事件綁定）？只描述 diff 裡實際看得到的行為差異，不要推測「使用者體驗會更好」之類 diff 沒有直接呈現的效果，也不要補上「為了提升穩定性／效能／安全性／解決某個 bug」這類 diff 無法直接證明的效益說明。
既有行為被修改時（數值、條件判斷、狀態切換等），一律寫成「由 A 改為 B」，把修改前後的實際值/條件都寫出來，不要只寫「調整了條件」「修改了門檻」這種看不出實際差異的空泛敘述。例如 timeout = 5000 改成 timeout = 10000，要寫「timeout 由 5000ms 調整為 10000ms」，而不是「調整了 timeout」。
這個「由 A 改為 B」格式只適用於「既有行為被修改」的情況；新增、刪除、搬移不要硬套這個格式——新增函式就寫「新增 xxx()」，搬移就寫「將 xxx() 移至 yyy」，不需要寫成「從不存在改為存在」這種不自然的敘述。
是否為資料模型調整（例如陣列改關聯表、欄位新增/移除）？
是否為單純格式調整（縮排、換行符轉換），若是，只需一行帶過，不要展開細節。
如果一個 hunk 的改動意圖不明顯（例如單純改了變數名稱，看不出動機），就如實描述「做了什麼改動」，不要編造「為什麼這樣改」的理由。寧可寫得保守精確，也不要寫得完整但失真。
函式或變數改名時，只有在 diff 中能確認所有呼叫端/引用處都已同步更新，才能寫「重新命名並同步更新引用」；如果只看到定義處改名、看不到（或無法確認）呼叫端有沒有跟著改，就只能寫「重新命名為 xxx」，不要多加「同步更新引用」這個沒有證據支持的結論。
4. 新增/刪除整份檔案
只有 .after、沒有 .before：視為新增檔案，在對應章節開頭註明「新增檔案」，並摘要其主要內容/用途。
只有 .before、沒有 .after：視為刪除檔案，在對應章節開頭註明「移除檔案」，並簡述被移除的主要功能。
5. 判斷 commit type（用於開頭前綴）
Feat: 新增功能／新增欄位／新增 UI 元素
Fix: 修正錯誤行為
Refactor: 重構既有邏輯、資料結構調整但外部行為大致不變
Style: 純樣式/格式調整（少見，通常會和其他變更合併，此時前綴用主要異動的 type）

若同時有多種性質的變更，以「本次變更的主要實際目的」判斷前綴，不要用「哪個影響比較大」這種主觀猜測來決定；如果無法判斷哪個是主要目的，優先採用能最保守涵蓋整體變更的前綴（通常是 Feat:），其餘變更照樣列在對應檔案段落下即可，不需要糾結前綴選誰。

如果 diff 明顯包含多個彼此不相關的功能變更（例如同時改了跟登入無關的兩個模組，內容看不出關聯），在標題摘要盡量涵蓋主要變更即可，並在 code block 之後補一句提醒，例如：「注意：本次改動包含多個不相關的變更，建議確認是否要拆成多個 commit。」不要為了湊出一句看起來連貫的摘要而勉強把不相關的變更硬掰成同一個目的。

6. 草擬 commit message

依照下方「輸出格式」組合成 commit message。

7. 自我核對（在輸出前，不要跳過這一步）

寫完草稿後，逐條比對每一個 bullet：

這個 bullet 提到的每一個函式名稱、id、class、變數名稱、欄位名稱，是否都能在該檔案的 diff 輸出中找到逐字對應？如果找不到，刪掉或修正這個 bullet，不要保留憑印象寫的內容。
這個 bullet 描述的行為變化，是否真的能從 +/- 行的程式邏輯推導出來？如果只是「看起來應該是這樣」但 diff 沒有直接證據，要改寫成更保守、更貼近 diff 實際內容的敘述。
是否有 hunk 的變更完全沒有反映在任何 bullet 裡？如果有，補上遺漏的項目。
純格式調整是否誤判成邏輯變更（或反之）？必要時回頭用 -w 版本 diff 再次確認，並確認沒有把搬移（Code Movement）誤判成刪除＋新增。
有沒有寫「同步更新引用」但其實沒看到呼叫端也跟著改？如果證據不足，把這句話拿掉，只保留「重新命名為 xxx」。
有沒有偷偷加了「提升穩定性／效能／使用者體驗／解決 bug」這類 diff 無法直接證明的效益字眼？如果有，刪掉或改寫成只描述實際行為變化。
如果這組 diff 包含多個互不相關的變更，是否已經在 code block 後加上提醒，而不是硬湊成一句連貫但失真的摘要？

確認無誤後才輸出最終 commit message。

輸出格式
<Type>: <一句話總結本次變更，繁體中文，涵蓋主要目的>

<檔名1，例如 app.js>

* <變更項目1，具體到函式/變數/id層級>
* <變更項目2>
* ...

<檔名2，例如 index.html>

* <變更項目1>
* ...

<檔名3，例如 styles.css>（若無變更則整段省略，不要寫「無變更」）

* <變更項目1>
* ...

格式規則：

標題行格式固定為 <Type>: <摘要>，例如 Feat: 新增物料管理 CRUD 功能與導覽權限控管、Refactor: 產品 BOM 改為關聯表結構，工單建立移除庫存/模具約束檢查並新增產品庫存累加。
摘要控制在一行內講完，允許用逗號或頓號連接多個重點，但不要超過約 40–50 字。
檔名區塊標題用還原後的實際檔名（app_js.before → app.js，index_html.before → index.html，styles_css.before → styles.css），不要用底線版檔名。
沒有變更的檔案（diff 完全相同，包含用 -w 確認後也相同）整段省略，不要列出來也不要寫「無變更」。
每個項目用 * 條列，一行一項，具體點出函式名稱（加反引號或原樣呈現）、id、class、欄位名稱等技術細節，讓熟悉 codebase 的人一看就懂改了什麼——但這些技術細節必須是「第 7 步自我核對」通過、diff 中確實存在的內容。
純格式/縮排/換行符調整只需一句話帶過（例如「整體縮排格式調整（4 空白改為 2 空白），結構未變」），不要逐行列舉。
全程使用繁體中文（台灣用語），程式相關的專有名詞（function、id、class、enum 等）可保留英文原文或加反引號標示。
不要在 commit message 內加入表情符號、簽名檔、Co-authored-by 等額外資訊，除非使用者要求。
最終輸出用單一 code block 包住整段 commit message，方便使用者一鍵複製；code block 前後不要加額外的分析文字或客套話（例如不要說「以下是 commit message：」），除非變更內容有需要特別提醒使用者注意的地方（例如發現某個變更可能是 bug、或第 7 步核對時發現 diff 內容不足以支撐某個原本想寫的結論而做了保守處理），才在 code block 之後補一句簡短提醒。
範例

輸入：使用者上傳 app_js.before / app_js.after，diff 顯示新增了 renderPreview() 內對 #submitWorkOrderBtn 的 disabled 狀態控制，以及 index_html.before/after 中該按鈕新增了 id="submitWorkOrderBtn"。

輸出：

Feat: 模具非閒置時停用工單送出按鈕

app.js

* renderPreview() 新增按鈕狀態控制邏輯：當所選組合無對應產品，或綁定模具狀態非 Idle 時，將 #submitWorkOrderBtn 設為 disabled，並調整透明度與游標樣式提示不可點擊；模具為 Idle 時恢復可點擊狀態

index.html

* 工單送出按鈕新增 id="submitWorkOrderBtn"，供 app.js 控制其啟用/停用狀態