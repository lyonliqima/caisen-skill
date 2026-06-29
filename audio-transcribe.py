#!/usr/bin/env python3
"""
音频转写脚本（whisper-cli + Metal GPU 加速）
使用 whisper-cpp 的 whisper-cli，Apple Silicon Metal 加速
安装: brew install whisper-cpp
模型: curl -L "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" -o ~/.cache/whisper/ggml-small.bin
"""

import sys
import os
import subprocess
import time

WHISPER_CLI = 'whisper-cli'
MODEL_PATH = os.path.expanduser('~/.cache/whisper/ggml-small.bin')


def main():
    audio_file = '/Users/weihaoli/Desktop/蔡森 skill/金錢爆0608.wav'
    output_base = '/Users/weihaoli/Desktop/蔡森 skill/money-burst-0608-transcript'
    output_file = output_base + '.txt'

    if not os.path.exists(audio_file):
        print(f"音频文件不存在: {audio_file}")
        print("请先用ffmpeg提取音频：")
        print(f"ffmpeg -i '{audio_file.replace('.wav','.mp4')}' -ar 16000 -ac 1 '{audio_file}'")
        sys.exit(1)

    if not os.path.exists(MODEL_PATH):
        print(f"模型不存在: {MODEL_PATH}")
        print("请下载模型：")
        print(f'curl -L "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" -o {MODEL_PATH}')
        sys.exit(1)

    # 获取音频时长
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', audio_file],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())
    mins = int(duration // 60)
    secs = int(duration % 60)

    print(f"音频: {os.path.basename(audio_file)}")
    print(f"时长: {mins}分{secs}秒")
    print(f"模型: {os.path.basename(MODEL_PATH)} (Metal GPU)")
    print(f"\n开始转写...\n")

    start_time = time.time()

    cmd = [
        WHISPER_CLI,
        '-m', MODEL_PATH,
        '-l', 'zh',
        '-f', audio_file,
        '-otxt',
        '-of', output_base,
    ]

    process = subprocess.run(cmd, capture_output=False)

    elapsed = time.time() - start_time
    elapsed_min = int(elapsed // 60)
    elapsed_sec = int(elapsed % 60)

    if process.returncode == 0 and os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            text = f.read()
        print(f"\n转写完成！耗时 {elapsed_min}分{elapsed_sec}秒")
        print(f"已保存到: {output_file}")
        print(f"总字数: {len(text)}")
        print(f"\n--- 前500字 ---")
        print(text[:500])
    else:
        print(f"\n转写失败，返回码: {process.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
