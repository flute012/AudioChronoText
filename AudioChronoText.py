import os
import json
import difflib
import time
import re
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from tkinter import messagebox
import threading
import tkinter.font as tkFont
from faster_whisper import WhisperModel
from pydub import AudioSegment

def clean_word(word):
    cleaned = re.sub(r'[^\w\s]', '', word)
    return cleaned.strip()

class AudioTranscriber:
    def __init__(self, model_name="large-v2", device="cpu"):
        device = "cpu"
        print(f"載入 Faster Whisper {model_name} 模型於 {device}...")
        try:
            self.model = WhisperModel(model_name, device=device)
            print("模型載入成功")
        except Exception as e:
            print(f"模型載入出錯: {e}")
            raise
        
    def transcribe_audio(self, audio_path, reference_text=None):
        if not os.path.isfile(audio_path):
            return {"error": f"找不到文件: {audio_path}"}
        print("使用 Faster Whisper 進行轉錄...")
        segments, info = self.model.transcribe(audio_path, word_timestamps=True)
        
        transcription = ""
        word_timestamps = []
        
        for segment in segments:
            transcription += segment.text + " "
            for word in segment.words:
                original_word = word.word.strip()
                cleaned_word = clean_word(original_word)
                
                if cleaned_word:
                    word_timestamps.append({
                        "word": cleaned_word,
                        "original_word": original_word, 
                        "start": round(word.start, 3),
                        "end": round(word.end, 3)
                    })

        transcription = transcription.strip()
        
        if reference_text:
            print("使用參考文本修正轉錄...")
            corrected_transcription, corrected_timestamps = self.correct_transcription(
                transcription, 
                reference_text, 
                word_timestamps
            )
            result = {
                "original_transcription": transcription,
                "corrected_transcription": corrected_transcription,
                "words": corrected_timestamps
            }
        else:
            result = {
                "transcription": transcription,
                "words": word_timestamps
            }
            
        return result
    
    def correct_transcription(self, transcription, reference_text, word_timestamps):

        trans_lower = transcription.lower()
        ref_lower = reference_text.lower()

        trans_words_raw = trans_lower.split()
        ref_words_raw = ref_lower.split()
        

        trans_words = [clean_word(w) for w in trans_words_raw]
        ref_words = [clean_word(w) for w in ref_words_raw]
        

        trans_words = [w for w in trans_words if w]
        ref_words = [w for w in ref_words if w]
        

        ref_original_map = {}
        for i, raw in enumerate(ref_words_raw):
            cleaned = clean_word(raw)
            if cleaned:
                ref_original_map[i] = raw
        

        matcher = difflib.SequenceMatcher(None, trans_words, ref_words)
        

        corrected_timestamps = []
        current_trans_idx = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':

                for k in range(i2 - i1):
                    if current_trans_idx < len(word_timestamps):
                        timestamp = {
                            "word": word_timestamps[current_trans_idx]["word"],
                            "start": round(word_timestamps[current_trans_idx]["start"], 3),
                            "end": round(word_timestamps[current_trans_idx]["end"], 3)
                        }

                        orig_idx = j1 + k
                        if orig_idx in ref_original_map:
                            timestamp["word"] = clean_word(ref_original_map[orig_idx])
                        
                        corrected_timestamps.append(timestamp)
                        current_trans_idx += 1
            
            elif tag == 'replace':

                trans_segment_len = i2 - i1
                ref_segment_len = j2 - j1
                
                if trans_segment_len > 0 and current_trans_idx < len(word_timestamps):

                    start_time = word_timestamps[current_trans_idx]["start"]
                    
                    if current_trans_idx + trans_segment_len - 1 < len(word_timestamps):
                        end_time = word_timestamps[current_trans_idx + trans_segment_len - 1]["end"]
                    else:
                        end_time = word_timestamps[-1]["end"]
                    

                    time_span = end_time - start_time
                    word_span = time_span / ref_segment_len if ref_segment_len > 0 else 0
                    
                    for k in range(ref_segment_len):
                        word_start = start_time + (k * word_span)
                        

                        orig_idx = j1 + k
                        orig_word = ref_original_map.get(orig_idx, f"word_{j1+k}")
                        cleaned_word = clean_word(orig_word)
                        
                        corrected_timestamps.append({
                            "word": cleaned_word,
                            "start": round(word_start, 3),
                            "end": round(word_start + word_span, 3)
                        })
                    
                    current_trans_idx += trans_segment_len
            
            elif tag == 'delete':

                current_trans_idx += (i2 - i1)
            
            elif tag == 'insert':

                if current_trans_idx > 0 or current_trans_idx < len(word_timestamps):

                    if current_trans_idx == 0:

                        next_time = word_timestamps[0]["start"]
                        prev_time = max(0, next_time - 0.5) 
                    elif current_trans_idx >= len(word_timestamps):

                        prev_time = word_timestamps[-1]["end"]
                        next_time = prev_time + 0.5 
                    else:

                        prev_time = word_timestamps[current_trans_idx-1]["end"]
                        next_time = word_timestamps[current_trans_idx]["start"]
                    
                    gap = next_time - prev_time
                    word_gap = gap / (j2 - j1) if j2 > j1 else 0.2  
                    
                    for k in range(j2 - j1):
                        word_start = prev_time + (k * word_gap)
                        
                        orig_idx = j1 + k
                        orig_word = ref_original_map.get(orig_idx, f"word_{j1+k}")
                        cleaned_word = clean_word(orig_word)
                        
                        corrected_timestamps.append({
                            "word": cleaned_word,
                            "start": round(word_start, 3),
                            "end": round(word_start + word_gap, 3)
                        })
        
        corrected_timestamps.sort(key=lambda x: x["start"])
        
        corrected_transcription = " ".join([w for w in reference_text.split()])
        
        return corrected_transcription, corrected_timestamps

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

class TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("語音轉錄工具")
        self.root.geometry("900x700")
        self.root.configure(bg="#f0f0f0")
        
        # 自定義字體
        self.title_font = tkFont.Font(family="微軟正黑體", size=16, weight="bold")
        self.normal_font = tkFont.Font(family="微軟正黑體", size=10)
        self.button_font = tkFont.Font(family="微軟正黑體", size=10, weight="bold")
        
        # 創建主框架
        self.main_frame = ttk.Frame(root, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 創建樣式
        self.style = ttk.Style()
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabel", background="#f0f0f0", font=self.normal_font)
        self.style.configure("TButton", font=self.button_font)
        self.style.configure("Title.TLabel", font=self.title_font)
        
        # 創建標題
        self.title_label = ttk.Label(
            self.main_frame, 
            text="語音轉錄工具", 
            style="Title.TLabel"
        )
        self.title_label.grid(row=0, column=0, columnspan=3, pady=10)
        
        # 音頻文件選擇部分
        self.audio_frame = ttk.LabelFrame(self.main_frame, text="音頻文件選擇 (僅支援MP3格式)", padding=10)
        self.audio_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5, padx=5)
        
        self.audio_path_var = tk.StringVar()
        self.audio_path_entry = ttk.Entry(self.audio_frame, textvariable=self.audio_path_var, width=50)
        self.audio_path_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        self.browse_button = ttk.Button(
            self.audio_frame, 
            text="瀏覽...", 
            command=self.browse_audio_file
        )
        self.browse_button.grid(row=0, column=1, padx=5, pady=5)
        
        # 參考文本框架
        self.ref_frame = ttk.LabelFrame(
            self.main_frame, 
            text="參考文本 (可選) - 可直接貼上純文字或上傳TXT文件", 
            padding=10
        )
        self.ref_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=5, padx=5)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(2, weight=1)
        
        self.ref_text = scrolledtext.ScrolledText(
            self.ref_frame, 
            wrap=tk.WORD, 
            width=80, 
            height=6, 
            font=self.normal_font
        )
        self.ref_text.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.ref_frame.columnconfigure(0, weight=1)
        self.ref_frame.rowconfigure(0, weight=1)

        self.browse_ref_button = ttk.Button(
            self.ref_frame, 
            text="從文件導入...", 
            command=self.browse_ref_file
        )
        self.browse_ref_button.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        
        self.clear_ref_button = ttk.Button(
            self.ref_frame, 
            text="清除參考文本", 
            command=self.clear_ref_text
        )
        self.clear_ref_button.grid(row=1, column=1, sticky="e", padx=5, pady=5)
        
        self.action_frame = ttk.Frame(self.main_frame, padding=5)
        self.action_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=5, padx=5)
        
        self.transcribe_button = ttk.Button(
            self.action_frame, 
            text="開始轉錄", 
            command=self.start_transcription
        )
        self.transcribe_button.grid(row=0, column=0, padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="準備就緒")
        self.status_label = ttk.Label(self.action_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=1, padx=5, pady=5)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.action_frame, 
            orient=tk.HORIZONTAL, 
            length=300, 
            mode="indeterminate", 
            variable=self.progress_var
        )
        self.progress_bar.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        self.action_frame.columnconfigure(2, weight=1)

        self.result_frame = ttk.LabelFrame(self.main_frame, text="轉錄結果", padding=10)
        self.result_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=5, padx=5)
        self.main_frame.rowconfigure(4, weight=2)
        
        self.result_text = scrolledtext.ScrolledText(
            self.result_frame, 
            wrap=tk.WORD, 
            width=80, 
            height=18, 
            font=self.normal_font
        )
        self.result_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.result_frame.columnconfigure(0, weight=1)
        self.result_frame.rowconfigure(0, weight=1)
        
        self.help_frame = ttk.LabelFrame(self.main_frame, text="使用說明", padding=5)
        self.help_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=5, padx=5)
        
        help_text = """1. 選擇 MP3 音頻文件 (僅支援MP3格式)。
2. 可選：輸入參考文本或從文件導入。
3. 點擊"開始轉錄"按鈕開始處理。
4. 處理完成後，結果將顯示在下方的文本框中，並自動保存為 TXT 和 JSON 文件。
5. 本工具使用 Whisper large-v2 模型，將在 CPU 上運行。"""
        
        self.help_label = ttk.Label(self.help_frame, text=help_text, justify=tk.LEFT)
        self.help_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.transcriber = None
        
    def browse_audio_file(self):
        filepath = filedialog.askopenfilename(
            title="選擇音頻文件",
            filetypes=[("MP3 文件", "*.mp3")]
        )
        if filepath:
            self.audio_path_var.set(filepath)
            
    def browse_ref_file(self):
        filepath = filedialog.askopenfilename(
            title="選擇參考文本文件",
            filetypes=[("文本文件", "*.txt")]
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.ref_text.delete(1.0, tk.END)
                self.ref_text.insert(tk.END, content)
            except Exception as e:
                messagebox.showerror("錯誤", f"無法讀取文件: {e}")
                
    def clear_ref_text(self):
        """清除參考文本"""
        self.ref_text.delete(1.0, tk.END)
    
    def start_transcription(self):
        """開始轉錄過程"""
        audio_path = self.audio_path_var.get().strip()
        
        if not audio_path:
            messagebox.showerror("錯誤", "請選擇音頻文件")
            return
            
        if not os.path.exists(audio_path):
            messagebox.showerror("錯誤", f"找不到音頻文件: {audio_path}")
            return
            
        reference_text = self.ref_text.get(1.0, tk.END).strip()
        if not reference_text:
            reference_text = None
        else:
            print(f"使用參考文本，長度: {len(reference_text)} 字符")

        self.transcribe_button.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.browse_ref_button.configure(state="disabled")

        self.progress_bar.start(10)
        self.status_var.set("正在準備轉錄...")

        threading.Thread(target=self.run_transcription, args=(audio_path, reference_text)).start()
        
    def run_transcription(self, audio_path, reference_text):

        try:

            self.root.after(0, lambda: self.status_var.set("正在載入模型..."))
            
            # 創建轉錄器
            if self.transcriber is None:
                self.transcriber = AudioTranscriber("large-v2", "cpu")
            
            # 更新界面
            self.root.after(0, lambda: self.status_var.set("正在進行轉錄..."))
            
            # 執行轉錄
            start_time = time.time()
            result = self.transcriber.transcribe_audio(audio_path, reference_text)
            elapsed_time = time.time() - start_time
            
            # 處理結果
            self.root.after(0, lambda: self.display_results(result, audio_path, elapsed_time))
            
        except Exception as e:
            error_msg = f"轉錄過程中發生錯誤: {str(e)}"
            self.root.after(0, lambda: self.show_error(error_msg))
            
    def display_results(self, result, audio_path, elapsed_time):
        """顯示轉錄結果"""
        # 停止進度條
        self.progress_bar.stop()
        
        # 更新狀態
        self.status_var.set(f"轉錄完成，用時 {elapsed_time:.2f} 秒")
        
        # 顯示結果
        self.result_text.delete(1.0, tk.END)
        
        if "error" in result:
            self.result_text.insert(tk.END, f"錯誤: {result['error']}\n")
        else:
            if "corrected_transcription" in result:
                self.result_text.insert(tk.END, "== 修正後的轉錄 ==\n\n")
                self.result_text.insert(tk.END, result["corrected_transcription"])
                self.result_text.insert(tk.END, "\n\n== 原始轉錄 ==\n\n")
                self.result_text.insert(tk.END, result["original_transcription"])
                
                # 保存結果
                output_file = f"{os.path.splitext(audio_path)[0]}_transcription.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("== 修正後的轉錄 ==\n\n")
                    f.write(result["corrected_transcription"])
                    f.write("\n\n== 單字時間戳 (已移除非文字字符) ==\n\n")
                    for item in result["words"]:
                        f.write(f"{format_timestamp(item['start'])} --> {format_timestamp(item['end'])}: {item['word']}")
                        f.write("\n")
                
                # 保存為新的 JSON 格式
                json_file = f"{os.path.splitext(audio_path)[0]}_transcription.json"
                json_data = {
                    "words": [
                        {
                            "word": item["word"],
                            "start": item["start"],
                            "end": item["end"]
                        } for item in result["words"]
                    ]
                }
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2)
                    
                # 顯示保存信息
                self.result_text.insert(tk.END, f"\n\n結果已保存至:\n{output_file}\n{json_file}")
                
            else:
                self.result_text.insert(tk.END, "== 轉錄 ==\n\n")
                self.result_text.insert(tk.END, result["transcription"])
                
                # 保存結果
                output_file = f"{os.path.splitext(audio_path)[0]}_transcription.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("== 轉錄 ==\n\n")
                    f.write(result["transcription"])
                    f.write("\n\n== 單字時間戳 (已移除非文字字符) ==\n\n")
                    for item in result["words"]:
                        f.write(f"{format_timestamp(item['start'])} --> {format_timestamp(item['end'])}: {item['word']}")
                        f.write("\n")
                
                # 保存為新的 JSON 格式
                json_file = f"{os.path.splitext(audio_path)[0]}_transcription.json"
                json_data = {
                    "words": [
                        {
                            "word": item["word"],
                            "start": item["start"],
                            "end": item["end"]
                        } for item in result["words"]
                    ]
                }
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2)
                    
                # 顯示保存信息
                self.result_text.insert(tk.END, f"\n\n結果已保存至:\n{output_file}\n{json_file}")
        
        # 重新啟用按鈕
        self.transcribe_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.browse_ref_button.configure(state="normal")
        
    def show_error(self, error_msg):
        """顯示錯誤信息"""
        # 停止進度條
        self.progress_bar.stop()
        
        # 更新狀態
        self.status_var.set("發生錯誤")
        
        # 顯示錯誤信息
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, error_msg)
        self.result_text.insert(tk.END, "\n\n請確保已安裝所有必要的 Python 包:\n")
        self.result_text.insert(tk.END, "pip install faster-whisper pydub numpy tkinter")
        
        # 重新啟用按鈕
        self.transcribe_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.browse_ref_button.configure(state="normal")

def main():
    root = tk.Tk()
    app = TranscriberApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
