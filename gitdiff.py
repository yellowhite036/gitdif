"""
git_diff_copy_gui.py

Pick changed files in a git repository, export their HEAD/current versions as
*.before and *.after, then send those pairs plus SKILL.md to a web LLM for a
Traditional Chinese commit message.

新增功能：
- 「暫存待送出清單」— 可以分別從不同資料夾/檔案，多次加入清單，
  最後再一次送出，藉此達成「跨資料夾選擇檔案」的效果。
- 記住上一次瀏覽的資料夾（僅限本次程式執行期間，暫時性），
  讓下次開啟選擇視窗時能接續上次的位置，減少來回切換資料夾的麻煩。
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass

if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(bundle_dir, "tcl", "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(bundle_dir, "tcl", "tk8.6"))

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


DEFAULT_LLM_URL = "https://chatgpt.com/"
PASTE_DELAY_SECONDS = 5


@dataclass
class DiffPair:
    rel_path: str
    before_path: str
    after_path: str
    is_new: bool = False


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_skill_md(repo_root=None):
    candidates = [
        os.path.join(app_dir(), "SKILL.md"),
        os.path.join(os.getcwd(), "SKILL.md"),
    ]
    if repo_root:
        candidates.append(os.path.join(repo_root, "SKILL.md"))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def read_all_bytes(path, retries=5, retry_delay=0.2):
    """讀取檔案完整內容，並確認實際讀到的位元組數與檔案大小一致。

    若讀到一半被截斷（例如檔案仍在被其他程式寫入、防毒軟體鎖檔、
    網路磁碟延遲等），會重試數次；重試後仍不一致就拋出例外，避免
    把殘缺內容送進 prompt。
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            expected_size = os.path.getsize(path)
            with open(path, "rb") as f:
                raw = f.read()

            if len(raw) == expected_size:
                return raw

            last_error = (
                f"讀取 {path} 時發現大小不一致："
                f"預期 {expected_size} bytes，實際讀到 {len(raw)} bytes"
                f"（第 {attempt}/{retries} 次嘗試）"
            )
        except OSError as exc:
            last_error = f"讀取 {path} 時發生錯誤：{exc}（第 {attempt}/{retries} 次嘗試）"

        if attempt < retries:
            time.sleep(retry_delay)

    raise RuntimeError(f"無法完整讀取檔案，已重試 {retries} 次仍失敗：{last_error}")


def read_text_file(path):
    raw = read_all_bytes(path)

    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def find_git_root(path):
    """Return the git repository root for a file or directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path if os.path.isdir(path) else os.path.dirname(path),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def file_exists_in_head(repo_root, rel_path):
    result = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def get_head_content(repo_root, rel_path):
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
    )
    return result.stdout


def is_file_modified(repo_root, rel_path):
    """Return whether a file differs from HEAD or is untracked."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", rel_path],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def unique_pair_paths(out_dir, rel_path, repo_prefix=None):
    """組出 .before / .after 的輸出路徑。

    當多個檔案（可能來自不同 git repository）要匯出到同一個共用資料夾時，
    加上 repo_prefix（通常是 repo 根目錄的資料夾名稱）可避免不同 repo
    但相對路徑相同的檔案互相覆蓋。
    """
    safe_name = rel_path.replace("/", "__").replace("\\", "__")
    if repo_prefix:
        safe_name = f"{repo_prefix}__{safe_name}"
    return (
        os.path.join(out_dir, safe_name + ".before"),
        os.path.join(out_dir, safe_name + ".after"),
    )


def process_single_file(repo_root, abs_file_path, out_dir, log, use_repo_prefix=False):
    rel_path = os.path.relpath(abs_file_path, repo_root).replace("\\", "/")
    repo_prefix = os.path.basename(os.path.normpath(repo_root)) if use_repo_prefix else None
    before_path, after_path = unique_pair_paths(out_dir, rel_path, repo_prefix=repo_prefix)

    is_new = not file_exists_in_head(repo_root, rel_path)

    if not is_new:
        content = get_head_content(repo_root, rel_path)
        with open(before_path, "wb") as f:
            f.write(content)

        written_size = os.path.getsize(before_path)
        if written_size != len(content):
            raise RuntimeError(
                f"寫入 {before_path} 時發生截斷：預期 {len(content)} bytes，"
                f"實際寫入 {written_size} bytes"
            )
        log(f"[before] {rel_path} -> {before_path}")
    else:
        open(before_path, "wb").close()
        log(f"[before] {rel_path} 為新增檔案，HEAD 中不存在")

    after_content = read_all_bytes(abs_file_path)
    with open(after_path, "wb") as dst:
        dst.write(after_content)

    # 寫入後再驗證一次輸出檔案大小，確認沒有寫到一半就被中斷
    written_size = os.path.getsize(after_path)
    if written_size != len(after_content):
        raise RuntimeError(
            f"寫入 {after_path} 時發生截斷：預期 {len(after_content)} bytes，"
            f"實際寫入 {written_size} bytes"
        )
    log(f"[after]  {rel_path} -> {after_path}")

    return DiffPair(rel_path=rel_path, before_path=before_path, after_path=after_path, is_new=is_new)


def collect_for_path(target_path, log, out_dir=None):
    repo_root = find_git_root(target_path)
    if not repo_root:
        raise RuntimeError("選取的位置不在 git repository 裡。")

    if out_dir is None:
        base_dir = os.path.dirname(target_path) if os.path.isfile(target_path) else target_path
        out_dir = os.path.join(base_dir, "git_diff_copy_output")
    os.makedirs(out_dir, exist_ok=True)

    pairs = []
    if os.path.isfile(target_path):
        rel_path = os.path.relpath(target_path, repo_root).replace("\\", "/")
        if not is_file_modified(repo_root, rel_path):
            log(f"[skip] {rel_path} 相對 HEAD 沒有變更，略過")
        else:
            pairs.append(process_single_file(repo_root, target_path, out_dir, log))
    else:
        for root, _, files in os.walk(target_path):
            if ".git" in root.split(os.sep):
                continue
            for fname in files:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, repo_root).replace("\\", "/")
                if is_file_modified(repo_root, rel_path):
                    pairs.append(process_single_file(repo_root, abs_path, out_dir, log))

    if not pairs:
        log("沒有找到相對 HEAD 有變更的檔案。")

    return repo_root, out_dir, pairs


def list_modified_files_in_dir(target_path):
    """走訪資料夾，回傳所有相對 HEAD 有變更（含未追蹤）的檔案絕對路徑清單。

    只列出清單，不做任何 before/after 匯出，供「暫存待送出清單」功能使用。
    """
    if not os.path.isdir(target_path):
        raise RuntimeError(f"{target_path} 不是資料夾。")

    repo_root = find_git_root(target_path)
    if not repo_root:
        raise RuntimeError(f"{target_path} 不在 git repository 裡。")

    results = []
    for root, _, files in os.walk(target_path):
        if ".git" in root.split(os.sep):
            continue
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, repo_root).replace("\\", "/")
            if is_file_modified(repo_root, rel_path):
                results.append(abs_path)

    return results


def collect_for_multiple_files(target_paths, log, out_dir=None):
    """處理一批檔案；這批檔案可以分別位於不同資料夾、甚至不同 git repository。

    不論檔案原本位於哪裡，產生的 .before / .after 都會統一寫入同一個
    out_dir。若沒有指定 out_dir，預設會用「清單中第一個檔案所在資料夾」底下
    的 git_diff_copy_output 作為這次批次共用的輸出資料夾。
    """
    if not target_paths:
        raise RuntimeError("沒有可處理的檔案。")

    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(target_paths[0]), "git_diff_copy_output")
    os.makedirs(out_dir, exist_ok=True)

    # 第一輪：先判斷每個檔案的 repo_root，並過濾掉沒變更 / 不在 repo 內的項目。
    # 這樣才能在真正處理前，知道這批檔案是否橫跨多個 repository。
    to_process = []
    repo_roots = set()
    skipped = []

    for target_path in target_paths:
        repo_root = find_git_root(target_path)
        if not repo_root:
            skipped.append(target_path)
            log(f"[skip] {target_path} is not inside a git repository")
            continue

        rel_path = os.path.relpath(target_path, repo_root).replace("\\", "/")
        if not is_file_modified(repo_root, rel_path):
            skipped.append(target_path)
            log(f"[skip] {target_path} 相對 HEAD 沒有變更，略過")
            continue

        to_process.append((repo_root, target_path))
        repo_roots.add(repo_root)

    # 一旦這批檔案橫跨超過一個 repo，就統一替所有檔名加上 repo 前綴，
    # 避免不同 repo 但相對路徑相同的檔案在同一個輸出資料夾裡互相覆蓋。
    use_repo_prefix = len(repo_roots) > 1

    pairs = [
        process_single_file(repo_root, target_path, out_dir, log, use_repo_prefix=use_repo_prefix)
        for repo_root, target_path in to_process
    ]

    if not pairs:
        raise RuntimeError("沒有可處理的檔案；選取的檔案可能不在 git repository 裡，或都沒有變更。")

    if skipped:
        log(f"[skip] {len(skipped)} file(s) were outside git repositories or unmodified")

    repo_root = sorted(repo_roots)[0] if repo_roots else None
    return repo_root, out_dir, pairs


def build_llm_prompt(pairs, skill_md_path):
    skill_md = read_text_file(skill_md_path) if skill_md_path else ""
    chunks = [
        "請依照下方 SKILL.md 的規則，根據 before/after 內容產生 git commit message。",
        "若檔案標示為「新增檔案」，代表該檔案在 HEAD 中不存在，請視為新增而非修改。",
        "請只回傳 commit message 本文，不要加說明，並請務必使用 Markdown code block 包裝您的回覆。",
        "",
        "===== SKILL.md =====",
        skill_md if skill_md else "(找不到 SKILL.md，請仍根據 diff 產生繁體中文 commit message。)",
        "",
        "===== BEFORE / AFTER FILES =====",
    ]

    for pair in pairs:
        after_text = read_text_file(pair.after_path)
        if pair.is_new:
            chunks.extend(
                [
                    "",
                    f"----- FILE: {pair.rel_path} (新增檔案，以下為完整內容) -----",
                    after_text,
                ]
            )
        else:
            before_text = read_text_file(pair.before_path)
            chunks.extend(
                [
                    "",
                    f"----- FILE: {pair.rel_path} / BEFORE -----",
                    before_text,
                    f"----- FILE: {pair.rel_path} / AFTER -----",
                    after_text,
                ]
            )

    return "\n".join(chunks)


def paste_text_with_hotkey(delay_seconds, wait_for_reply, coord_x, coord_y, log=None, set_clip_cb=None):
    time.sleep(delay_seconds)
    try:
        is_win = sys.platform.startswith("win")
        
        if is_win:
            import ctypes
            user32 = ctypes.windll.user32
            keybd_event = user32.keybd_event
            ctrl = 0x11
            v_key = 0x56
            enter = 0x0D
            keyup = 0x0002

        def do_paste():
            if is_win:
                keybd_event(ctrl, 0, 0, 0)
                keybd_event(v_key, 0, 0, 0)
                keybd_event(v_key, 0, keyup, 0)
                keybd_event(ctrl, 0, keyup, 0)
            elif sys.platform == "darwin":
                subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'], check=False)
            else:
                subprocess.run(["xdotool", "key", "ctrl+v"], check=False)

        def do_enter():
            if is_win:
                keybd_event(enter, 0, 0, 0)
                keybd_event(enter, 0, keyup, 0)
            elif sys.platform == "darwin":
                subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], check=False)
            else:
                subprocess.run(["xdotool", "key", "Return"], check=False)

        # 1. 貼上大量內容 (如果過長，ChatGPT 會轉成檔案附件)
        do_paste()
        time.sleep(1.0)
        
        # 2. 若 ChatGPT 轉成附件，需要一段短語來觸發它執行
        if set_clip_cb:
            short_prompt = "請根據上述或附檔內容與 SKILL.md 規則，產出 git commit message。只回傳 commit message 本文，不要加說明，並請務必使用 Markdown code block 包裝您的回覆。"
            set_clip_cb(short_prompt)
            time.sleep(0.5)
            do_paste()
            time.sleep(0.5)

        # 3. 送出
        do_enter()

        if log:
            log("已嘗試貼上 prompt 並送出。")

        if wait_for_reply > 0 and (coord_x > 0 or coord_y > 0):
            if log:
                log(f"等待 {wait_for_reply} 秒後，將點擊 ({coord_x}, {coord_y}) 進行複製...")
            time.sleep(wait_for_reply)

            if is_win:
                user32.SetCursorPos(coord_x, coord_y)
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            elif sys.platform == "darwin":
                subprocess.run(["osascript", "-e", f'tell application "System Events" to click at {{{coord_x}, {coord_y}}}'], check=False)
            else:
                subprocess.run(["xdotool", "mousemove", str(coord_x), str(coord_y), "click", "1"], check=False)

            if log:
                log("已嘗試自動點擊複製按鈕。")
    except Exception as exc:
        if log:
            log(f"自動操作失敗：{exc}")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Git before/after commit message helper")
        root.geometry("820x760")
        self.last_prompt = ""
        self.ignored_prompts = set()
        self.waiting_for_response = False

        # 暫存待送出清單（本次程式執行期間有效，關閉程式即清空）
        self.pending_paths = []
        # 暫時記住上一次瀏覽的資料夾，方便下次選檔/選資料夾時接續同一位置
        self.last_browse_dir = None

        top_frame = tk.Frame(root)
        top_frame.pack(fill=tk.X, padx=10, pady=(10, 4))

        tk.Label(top_frame, text="LLM URL").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar(value=DEFAULT_LLM_URL)
        tk.Entry(top_frame, textvariable=self.url_var, width=70).grid(row=0, column=1, sticky="ew", padx=6, columnspan=2)
        top_frame.columnconfigure(1, weight=1)

        tk.Label(top_frame, text="統一輸出資料夾").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.output_dir_var = tk.StringVar(value="")
        tk.Entry(top_frame, textvariable=self.output_dir_var, width=58).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(4, 0)
        )
        tk.Button(top_frame, text="瀏覽...", command=self.browse_output_dir).grid(
            row=1, column=2, sticky="w", pady=(4, 0)
        )
        tk.Label(
            top_frame,
            text="留空 = 自動使用「本次選取的第一個檔案所在資料夾」作為這次批次共用的輸出資料夾。",
            fg="gray40",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        settings_frame = tk.Frame(root)
        settings_frame.pack(fill=tk.X, padx=10, pady=4)

        tk.Label(settings_frame, text="生成等待時間(秒):").grid(row=0, column=0, sticky="w")
        self.wait_reply_var = tk.IntVar(value=15)
        tk.Entry(settings_frame, textvariable=self.wait_reply_var, width=5).grid(row=0, column=1, padx=4)

        tk.Label(settings_frame, text="複製按鈕座標 X:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.coord_x_var = tk.IntVar(value=0)
        tk.Entry(settings_frame, textvariable=self.coord_x_var, width=5).grid(row=0, column=3, padx=4)

        tk.Label(settings_frame, text="Y:").grid(row=0, column=4, sticky="w")
        self.coord_y_var = tk.IntVar(value=0)
        tk.Entry(settings_frame, textvariable=self.coord_y_var, width=5).grid(row=0, column=5, padx=4)

        tk.Button(settings_frame, text="抓取滑鼠座標 (3秒後)", command=self.capture_mouse_coords).grid(row=0, column=6, padx=(10, 0))

        # ---- 原本的「單次選取，立即送出」按鈕（維持不變） ----
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=(8, 2))

        tk.Label(btn_frame, text="立即送出：").grid(row=0, column=0, padx=(0, 4))
        tk.Button(btn_frame, text="選單一檔案", width=16, command=self.choose_file).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="選多個檔案", width=16, command=self.choose_files).grid(row=0, column=2, padx=5)
        tk.Button(btn_frame, text="選資料夾", width=16, command=self.choose_folder).grid(row=0, column=3, padx=5)
        tk.Button(btn_frame, text="等待剪貼簿回傳", width=18, command=self.start_waiting_for_response).grid(
            row=0, column=4, padx=5
        )

        # ---- 新增：跨資料夾暫存清單 ----
        pending_outer = tk.LabelFrame(root, text="跨資料夾暫存清單（可分批從不同資料夾加入，最後一次送出）")
        pending_outer.pack(fill=tk.BOTH, expand=False, padx=10, pady=(6, 4))

        pending_btn_frame = tk.Frame(pending_outer)
        pending_btn_frame.pack(fill=tk.X, padx=6, pady=4)

        tk.Button(pending_btn_frame, text="加入檔案", width=14, command=self.add_single_file_to_pending).grid(
            row=0, column=0, padx=3
        )
        tk.Button(pending_btn_frame, text="加入多個檔案", width=14, command=self.add_multiple_files_to_pending).grid(
            row=0, column=1, padx=3
        )
        tk.Button(pending_btn_frame, text="加入資料夾內變更檔案", width=20, command=self.add_folder_to_pending).grid(
            row=0, column=2, padx=3
        )
        tk.Button(pending_btn_frame, text="移除選取項目", width=14, command=self.remove_selected_pending).grid(
            row=0, column=3, padx=3
        )
        tk.Button(pending_btn_frame, text="清空清單", width=10, command=self.clear_pending).grid(
            row=0, column=4, padx=3
        )

        pending_list_frame = tk.Frame(pending_outer)
        pending_list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        pending_scrollbar = tk.Scrollbar(pending_list_frame, orient=tk.VERTICAL)
        self.pending_listbox = tk.Listbox(
            pending_list_frame, height=6, selectmode=tk.EXTENDED, yscrollcommand=pending_scrollbar.set
        )
        pending_scrollbar.config(command=self.pending_listbox.yview)
        self.pending_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pending_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.send_pending_btn = tk.Button(
            pending_outer, text="送出跨資料夾清單 (0)", command=self.send_pending
        )
        self.send_pending_btn.pack(padx=6, pady=(0, 6), anchor="e")

        tk.Label(root, text="Log").pack(anchor="w", padx=10)
        self.log_box = scrolledtext.ScrolledText(root, width=92, height=14)
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 8))

        tk.Label(root, text="Commit message 回傳").pack(anchor="w", padx=10)
        self.result_box = scrolledtext.ScrolledText(root, width=92, height=8)
        self.result_box.pack(fill=tk.BOTH, expand=False, padx=10, pady=(2, 10))

    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.root.update_idletasks()

    def set_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def set_result(self, text):
        self.result_box.delete("1.0", tk.END)
        self.result_box.insert(tk.END, text.strip() + "\n")
        self.result_box.see(tk.END)

    def browse_output_dir(self):
        path = filedialog.askdirectory(
            title="選擇統一輸出資料夾", initialdir=self.output_dir_var.get().strip() or self.last_browse_dir or None
        )
        if path:
            self.output_dir_var.set(path)
            self.log(f"已設定統一輸出資料夾：{path}")

    def get_output_dir(self, fallback_paths):
        """回傳這次批次要使用的共用輸出資料夾。

        若使用者在「統一輸出資料夾」欄位有填值，一律使用該資料夾（不論檔案原本
        位於哪裡）；否則預設用 fallback_paths 中第一個檔案所在資料夾，讓同一批次
        的所有檔案仍然共用同一個輸出資料夾。
        """
        configured = self.output_dir_var.get().strip()
        if configured:
            os.makedirs(configured, exist_ok=True)
            return configured
        if fallback_paths:
            base = fallback_paths[0]
            base_dir = os.path.dirname(base) if os.path.isfile(base) else base
            return os.path.join(base_dir, "git_diff_copy_output")
        return None

    def capture_mouse_coords(self):
        self.log("請將滑鼠移至複製按鈕上方，3秒後將自動記錄座標...")
        self.root.after(3000, self._do_capture_mouse)
        
    def _do_capture_mouse(self):
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        self.coord_x_var.set(x)
        self.coord_y_var.set(y)
        self.log(f"已記錄滑鼠座標：({x}, {y})")

    # ------------------------------------------------------------------
    # 跨資料夾暫存清單
    # ------------------------------------------------------------------
    def _update_pending_listbox(self):
        self.pending_listbox.delete(0, tk.END)
        for p in self.pending_paths:
            self.pending_listbox.insert(tk.END, p)
        self.send_pending_btn.config(text=f"送出跨資料夾清單 ({len(self.pending_paths)})")

    def _remember_browse_dir(self, path):
        if not path:
            return
        self.last_browse_dir = path if os.path.isdir(path) else os.path.dirname(path)

    def _add_paths_to_pending(self, paths):
        added = 0
        for p in paths:
            if p not in self.pending_paths:
                self.pending_paths.append(p)
                added += 1
        if paths:
            self._remember_browse_dir(paths[-1])
        self._update_pending_listbox()
        self.log(f"已加入 {added} 個檔案到暫存清單，目前共 {len(self.pending_paths)} 個（略過 {len(paths) - added} 個重複項目）。")

    def add_single_file_to_pending(self):
        path = filedialog.askopenfilename(title="加入檔案到暫存清單", initialdir=self.last_browse_dir or None)
        if path:
            self._add_paths_to_pending([path])

    def add_multiple_files_to_pending(self):
        paths = filedialog.askopenfilenames(title="加入多個檔案到暫存清單", initialdir=self.last_browse_dir or None)
        if paths:
            self._add_paths_to_pending(list(paths))

    def add_folder_to_pending(self):
        path = filedialog.askdirectory(title="加入資料夾內有變更的檔案", initialdir=self.last_browse_dir or None)
        if not path:
            return
        try:
            files = list_modified_files_in_dir(path)
        except Exception as exc:
            messagebox.showerror("錯誤", str(exc))
            return

        self._remember_browse_dir(path)
        if not files:
            self.log(f"{path} 內沒有找到相對 HEAD 有變更的檔案。")
            return
        self._add_paths_to_pending(files)

    def remove_selected_pending(self):
        selected = list(self.pending_listbox.curselection())
        if not selected:
            return
        for idx in reversed(selected):
            del self.pending_paths[idx]
        self._update_pending_listbox()
        self.log(f"已移除 {len(selected)} 個項目，暫存清單剩 {len(self.pending_paths)} 個。")

    def clear_pending(self):
        if not self.pending_paths:
            return
        self.pending_paths = []
        self._update_pending_listbox()
        self.log("已清空暫存清單。")

    def send_pending(self):
        if not self.pending_paths:
            messagebox.showwarning("清單是空的", "請先用「加入檔案／加入多個檔案／加入資料夾內變更檔案」把要送出的檔案加入清單。")
            return
        try:
            out_dir = self.get_output_dir(self.pending_paths)
            repo_root, out_dir, pairs = collect_for_multiple_files(list(self.pending_paths), self.log, out_dir=out_dir)
            self.send_pairs_to_llm(repo_root, out_dir, pairs)
        except Exception as exc:
            messagebox.showerror("錯誤", str(exc))

    # ------------------------------------------------------------------
    # 送出到 LLM 與等待回傳（原本邏輯，不變）
    # ------------------------------------------------------------------
    def send_pairs_to_llm(self, repo_root, out_dirs, pairs):
        if not pairs:
            messagebox.showwarning("沒有變更", "沒有可送出的 before/after 內容。")
            return

        skill_md_path = find_skill_md(repo_root)
        prompt = build_llm_prompt(pairs, skill_md_path)
        self.last_prompt = prompt
        self.set_clipboard(prompt)

        if skill_md_path:
            self.log(f"已讀取 SKILL.md：{skill_md_path}")
        else:
            self.log("找不到 SKILL.md，仍會送出 before/after 內容。")

        if isinstance(out_dirs, str):
            out_dir_text = out_dirs
        else:
            out_dir_text = "\n".join(out_dirs)
        self.log(f"輸出位置：\n{out_dir_text}")
        self.log(f"已複製 prompt 到剪貼簿，共 {len(prompt):,} 字元。")

        url = self.url_var.get().strip() or DEFAULT_LLM_URL
        webbrowser.open(url)
        self.log(f"已開啟瀏覽器：{url}")
        self.log(f"{PASTE_DELAY_SECONDS} 秒後會嘗試自動貼上並送出。")

        self.ignored_prompts.add(prompt.strip())

        def safe_set_clip(text):
            self.ignored_prompts.add(text.strip())
            self.root.after(0, lambda: self.set_clipboard(text))

        wait_time = self.wait_reply_var.get()
        cx = self.coord_x_var.get()
        cy = self.coord_y_var.get()
        threading.Thread(
            target=paste_text_with_hotkey, 
            args=(PASTE_DELAY_SECONDS, wait_time, cx, cy, self.log, safe_set_clip), 
            daemon=True
        ).start()
        self.start_waiting_for_response()

        messagebox.showinfo(
            "已送出 prompt",
            "已複製 before/after + SKILL.md 並開啟 LLM 網頁。\n"
            "若沒有自動貼上，請在網頁輸入框按 Ctrl+V 後送出。\n\n"
            "產生完成後複製 commit message，程式會自動顯示在下方。",
        )

    def start_waiting_for_response(self):
        if self.waiting_for_response:
            self.log("已經在等待剪貼簿回傳。")
            return
        self.waiting_for_response = True
        self.log("開始等待剪貼簿中的 commit message 回傳。")
        self.root.after(1000, self.poll_clipboard_response)

    def poll_clipboard_response(self):
        if not self.waiting_for_response:
            return

        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""

        normalized = text.strip()

        # 過濾可能存在的 Markdown code block 標籤 (例如 ``` 或 ```markdown)
        if normalized.startswith("```"):
            lines = normalized.split("\n")
            if len(lines) > 1 and lines[0].startswith("```"):
                lines = lines[1:]
            if len(lines) > 0 and lines[-1].strip() == "```":
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()

        if normalized and normalized not in getattr(self, "ignored_prompts", set()) and normalized != self.last_prompt.strip():
            self.waiting_for_response = False
            self.set_result(normalized)
            self.log("已從剪貼簿取得 commit message。")
            return

        self.root.after(1000, self.poll_clipboard_response)

    # ------------------------------------------------------------------
    # 原本的「單次選取，立即送出」流程（不變）
    # ------------------------------------------------------------------
    def choose_file(self):
        path = filedialog.askopenfilename(title="選擇檔案", initialdir=self.last_browse_dir or None)
        if path:
            self._remember_browse_dir(path)
            self.log(f"選取檔案：{path}")
            try:
                out_dir = self.get_output_dir([path])
                repo_root, out_dir, pairs = collect_for_path(path, self.log, out_dir=out_dir)
                self.send_pairs_to_llm(repo_root, out_dir, pairs)
            except Exception as exc:
                messagebox.showerror("錯誤", str(exc))

    def choose_files(self):
        paths = filedialog.askopenfilenames(title="選擇多個檔案", initialdir=self.last_browse_dir or None)
        if paths:
            self._remember_browse_dir(paths[-1])
            self.log(f"選取 {len(paths)} 個檔案")
            for path in paths:
                self.log(f"  - {path}")
            try:
                out_dir = self.get_output_dir(list(paths))
                repo_root, out_dir, pairs = collect_for_multiple_files(list(paths), self.log, out_dir=out_dir)
                self.send_pairs_to_llm(repo_root, out_dir, pairs)
            except Exception as exc:
                messagebox.showerror("錯誤", str(exc))

    def choose_folder(self):
        path = filedialog.askdirectory(title="選擇資料夾", initialdir=self.last_browse_dir or None)
        if path:
            self._remember_browse_dir(path)
            self.log(f"選取資料夾：{path}")
            try:
                out_dir = self.get_output_dir([path])
                repo_root, out_dir, pairs = collect_for_path(path, self.log, out_dir=out_dir)
                self.send_pairs_to_llm(repo_root, out_dir, pairs)
            except Exception as exc:
                messagebox.showerror("錯誤", str(exc))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()