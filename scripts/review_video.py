#!/usr/bin/env python3
"""本地视频全帧索引、分层审阅与证据记录。使用 --help 查看命令。"""
import argparse
import json
import os
from pathlib import Path
import sys

from vor_store import (candidate_manifest, database, dump, export_records, focus, get_meta, import_records,
                       record_view, select_candidates, status, validate)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    doctor = commands.add_parser('doctor', help='检查本地 Python、图像库及 FFmpeg 环境。')
    doctor.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    doctor.add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    subs = {}
    for name, help_text in {
        'scan': '索引原始时间戳，流式计算全部 RGB 帧，支持恢复。',
        'select': '根据已有指标选择候选画面。',
        'plan': '生成全时间线变化簇与代表画面。',
        'intervals': '列出人工区间映射、抽查需求和语言线索。',
        'sheet': '将已抽取的证据组成概览拼图。',
        'record-sheet-view': '按 overview 粒度登记实际展示的面板。',
        'tracks': '查询本地音轨与字幕轨。',
        'subtitles': '解析 SRT/VTT/内嵌文本字幕，并按原始 PTS 对齐。',
        'transcript': '导入带时间基准的转写 JSON，保留原文和译文。',
        'candidates': '列出候选时间、原因、路径和阶段进度。',
        'focus': '按原始时间秒数为具体疑点追加候选。',
        'extract': '抽取证据 PNG，并核对源像素哈希。',
        'crop': '裁剪证据并保留源帧身份。',
        'record-view': '登记图片工具调用引用与视觉观察。',
        'import-records': '按 ID 导入步骤与疑点，保存历史。',
        'status': '分别报告计算、候选、查看登记和后续范围。',
        'validate': '检查源文件与记录完整性，报告审阅完成度。',
        'audit': '检查分层/严格覆盖、操作衔接、抽查与复核。',
        'export': '从当前记录生成 JSON、逐帧数据和报告。'
    }.items():
        subs[name] = commands.add_parser(name, help=help_text)
        subs[name].add_argument('--work', required=True, type=Path, help='本视频专用的审阅目录。')
    s = subs['scan']
    s.add_argument('video', type=Path)
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    s.add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    s.add_argument('--tile-size', type=int, default=32)
    s.add_argument('--pixel-threshold', type=int, default=8)
    s.add_argument('--checkpoint-frames', type=int, default=100)
    s.add_argument('--max-new-frames', type=int, help='本次新增计算帧预算，达到后保存进度。')
    s = subs['select']
    s.add_argument('--mode', choices=['layered', 'coverage', 'changes'], default='layered',
                   help='layered 生成概览分组，coverage 保留全部连续 RGB 状态。')
    s.add_argument('--anchor-seconds', type=float, default=5.0)
    s.add_argument('--global-threshold', type=float, default=2.0)
    s.add_argument('--local-threshold', type=float, default=0.8)
    s.add_argument('--min-changed-pixels', type=int, default=8)
    s.add_argument('--context-frames', type=int, default=1)
    s.add_argument('--pixel-threshold', type=int, help='与扫描阈值一致；新扫描参数使用新审阅目录。')
    s = subs['candidates']
    s.add_argument('--pending', action='store_true')
    s.add_argument('--start', type=float)
    s.add_argument('--end', type=float)
    s = subs['focus']
    s.add_argument('--start', type=float, required=True)
    s.add_argument('--end', type=float, required=True)
    s.add_argument('--stride', type=int, default=1)
    s.add_argument('--reason', required=True)
    s = subs['extract']
    group = s.add_mutually_exclusive_group(required=True)
    group.add_argument('--candidates', action='store_true')
    group.add_argument('--frames', help='原始 0 起始帧号，逗号分隔。')
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    s = subs['crop']
    s.add_argument('--asset', required=True)
    s.add_argument('--box', required=True, help='原图像素坐标 x0,y0,x1,y1，右/下边界为开区间。')
    s = subs['record-view']
    s.add_argument('--asset', required=True)
    s.add_argument('--actor', required=True)
    s.add_argument('--tool', required=True, choices=['view_image', 'read_image', 'image_tool', 'visible_attachment'])
    s.add_argument('--trace', required=True, help='实际图片调用或消息引用，例如 read_image#msg-42。')
    s.add_argument('--observation', required=True, help='实际可见内容与待辨认区域。')
    subs['import-records'].add_argument('records', type=Path)
    subs['plan'].add_argument('--max-span', type=float, default=15.0, help='概览分组的上下文时长（秒）。')
    s = subs['sheet']
    s.add_argument('--frames', required=True)
    s.add_argument('--thumb-width', type=int, default=480)
    s.add_argument('--columns', type=int, default=4)
    s = subs['record-sheet-view']
    s.add_argument('--sheet', required=True)
    s.add_argument('--actor', required=True)
    s.add_argument('--trace', required=True)
    s.add_argument('--observations', required=True, type=Path, help='JSON 对象：已展示资产 ID 对应逐图观察。')
    subs['tracks'].add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    s = subs['subtitles']
    s.add_argument('source', type=Path)
    s.add_argument('--offset', type=float, default=0.0, help='original_video_time = subtitle_time + offset')
    s.add_argument('--language', default='und')
    s.add_argument('--stream', type=int, default=0, help='文本字幕流 s:N 的序号。')
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    subs['transcript'].add_argument('source', type=Path)
    subs['validate'].description = ('valid 表示源文件、证据与记录完整性；review_complete 表示候选查看及当前模式复核门禁完成。'
                                     '默认退出码按 valid 返回 0/1；--require-coverage 将审阅完成度加入退出状态。')
    subs['validate'].add_argument('--require-coverage', action='store_true',
                                  help='要求完整审阅；待完成时 valid=false，退出码 1。')
    for name in ('validate', 'export'):
        subs[name].add_argument('--rehash-source', action='store_true', help='本次重新计算源视频完整 SHA-256。')
    subs['validate'].add_argument('--mode', choices=['layered','strict'])
    subs['audit'].add_argument('--mode', choices=['layered','strict'], help='默认使用库内模式；旧库保留 strict。')
    subs['audit'].add_argument('--queue', action='store_true', help='把建议复查帧追加到候选队列。')
    subs['audit'].add_argument('--summary', action='store_true', help='输出计数与复核状态摘要。')
    return p


def main():
    args = parser().parse_args()
    try:
        if args.command == 'doctor':
            from vor_environment import diagnose
            result = diagnose(args.ffmpeg, args.ffprobe)
            print(dump(result))
            return 0 if result['ready'] else 1
        # Help and diagnosis must work even before optional runtime packages exist.
        from vor_media import crop, extract, scan
        from vor_audit import audit_omissions
        from vor_layers import prepare, manifest, make_sheet, record_sheet_view
        from vor_language import tracks, import_subtitles, import_transcript
        with database(args.work, create=args.command == 'scan') as conn:
            command = args.command
            if command == 'scan':
                result = scan(conn, args.work, args.video, args.ffmpeg, args.ffprobe, args.tile_size,
                              args.pixel_threshold, args.checkpoint_frames, args.max_new_frames)
            elif command == 'select':
                if args.pixel_threshold is not None and args.pixel_threshold != get_meta(conn, 'scan_config')['pixel_threshold']:
                    raise ValueError('pixel-threshold differs from stored metrics; run scan in a new directory.')
                result = select_candidates(conn, args.anchor_seconds, args.global_threshold,
                                           args.local_threshold, args.min_changed_pixels, args.context_frames, args.mode)
                if args.mode == 'layered':
                    prepare(conn,args.work)
            elif command == 'plan':
                result = prepare(conn,args.work,max_span=args.max_span)
            elif command == 'intervals':
                result = manifest(conn)
            elif command == 'sheet':
                result = make_sheet(conn,args.work,[int(n) for n in args.frames.split(',')],args.thumb_width,args.columns)
            elif command == 'record-sheet-view':
                result = record_sheet_view(conn,args.work,args.sheet,args.actor,args.trace,
                                           json.loads(args.observations.read_text(encoding='utf-8-sig')))
            elif command == 'tracks':
                result = tracks(conn,args.ffprobe)
            elif command == 'subtitles':
                result = import_subtitles(conn,args.work,args.source,args.offset,args.language,args.stream,args.ffmpeg)
            elif command == 'transcript':
                result = import_transcript(conn,args.work,args.source)
            elif command == 'focus':
                result = focus(conn, args.start, args.end, args.reason, args.stride)
            elif command == 'candidates':
                result = candidate_manifest(conn, args.work, args.pending, args.start, args.end)
            elif command == 'extract':
                frames = ([r[0] for r in conn.execute('SELECT frame_no FROM candidates ORDER BY frame_no')]
                          if args.candidates else [int(n) for n in args.frames.split(',')])
                result = extract(conn, args.work, frames, args.ffmpeg)
            elif command == 'crop':
                box = tuple(int(n) for n in args.box.split(','))
                if len(box) != 4:
                    raise ValueError('Crop requires exactly four coordinates.')
                result = crop(conn, args.work, args.asset, box)
            elif command == 'record-view':
                result = record_view(conn, args.work, args.asset, args.actor, args.tool, args.trace, args.observation)
            elif command == 'import-records':
                result = import_records(conn, args.records)
            elif command == 'validate':
                result = validate(conn, args.work, args.require_coverage, args.mode, args.rehash_source)
            elif command == 'audit':
                result = audit_omissions(conn, args.work, queue=args.queue, mode=args.mode)
                if args.summary:
                    result = {key: result[key] for key in ['snapshot', 'summary', 'records_ready_for_omission_review',
                              'omission_review', 'review_gate_passed_recorded', 'semantic_completeness_proven', 'assurance']}
            elif command == 'export':
                result = export_records(conn, args.work, args.rehash_source)
            else:
                result = status(conn)
            print(dump(result))
            return 1 if command == 'validate' and not result['valid'] else 0
    except KeyboardInterrupt:
        print(dump({'error': 'Interrupted; committed rows retained. Run status then resume scan.'}))
        return 130
    except ModuleNotFoundError as exc:
        print(dump({'error': str(exc), 'type': type(exc).__name__,
                    'hint': 'Run doctor with the same Python executable, then install the missing requirements.'}))
        return 1
    except Exception as exc:
        result = {'error': str(exc), 'type': type(exc).__name__}
        if getattr(exc, 'code', None):
            result['code'] = exc.code
        print(dump(result))
        return 1


if __name__ == '__main__':
    sys.exit(main())
