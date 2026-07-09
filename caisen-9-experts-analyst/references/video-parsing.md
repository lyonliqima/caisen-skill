# 第0.5步：视频内容解析（当用户提供视频文件时）

> 本细节从主 SKILL.md 抽出，避免编排器膨胀。主文件只留一句指针 + 「L4 且用户提供视频时执行」。

当用户附加了 `.mp4`/`.mov`/`.mkv` 视频文件时，必须先解析视频内容，作为第0步的补充背景资料。

**执行流程**：

1. **提取关键帧**（画面分析）：
   ```bash
   # 每30秒提取一帧，保存到与视频同名的frames目录
   mkdir -p "{video_name}-frames"
   ffmpeg -i "{video_path}" -vf "fps=1/30" -q:v 2 "{video_name}-frames/frame_%03d.jpg"
   ```

2. **逐批阅读关键帧**（用 Read 工具）：
   - 每批读6帧（frame_001~006、007~012...），覆盖全视频
   - 提取屏幕上的文字标题、数据图表、地图信息
   - 记录每个时段讨论的主题和数据点

3. **提取音频并转写**（语音分析）：
   ```bash
   # 提取音频（16kHz单声道WAV）
   ffmpeg -i "{video_path}" -ar 16000 -ac 1 "{video_name}.wav"
   # 转写（优先whisper，备选macOS原生）
   python3 -c "
   import whisper
   model = whisper.load_model('base')
   result = model.transcribe('{video_name}.wav', language='zh')
   with open('{video_name}-transcript.txt', 'w') as f:
       f.write(result['text'])
   print(result['text'][:500])
   "
   ```

4. **读取转写文本**（用 Read 工具），提取：
   - 主持人口头分析逻辑和判断
   - 口头提到的具体数据和时间节点
   - 口头操作建议

5. **整合到分析背景**：
   - 视频中的画面数据 → 作为第0步新闻背景的补充
   - 视频中的分析逻辑 → 作为对应专家视角的参考素材
   - 视频中的观点 → 应用时间衰减权重（见第4步规则）
   - **区分方法论与观点**：方法论永不过期，观点随时间衰减

**视频分析输出格式**（内部记录，不单独生成文件）：
```
## 视频解析摘要
- 视频名称：xxx
- 时长：xx分钟
- 核心主题：xxx
- 关键数据点：[列表]
- 主持人核心判断：[列表]
- 方法论提炼：[可复用的分析工具]
- 具体观点：[带时间衰减标注]
```
