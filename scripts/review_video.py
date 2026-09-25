#!/usr/bin/env python3
"""Local full-frame scan and evidence ledger. Run --help; no model API is called."""
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
    doctor = commands.add_parser('doctor', help='Check local dependencies without creating a review or testing host vision.')
    doctor.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    doctor.add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    subs = {}
    for name, help_text in {
        'scan': 'Index original timestamps and stream every RGB frame, or resume.',
        'select': 'Choose candidates from stored metrics; no visual review is implied.',
        'plan': 'Prepare full-timeline change clusters and representative overview frames.',
        'intervals': 'List authored interval mappings, sample requirements and language clues.',
        'sheet': 'Compose extracted frames as an overview sheet; does not record viewing.',
        'record-sheet-view': 'Record ACTUALLY displayed panels with overview granularity.',
        'tracks': 'Inspect local audio and subtitle tracks; no ASR is started.',
        'subtitles': 'Decode SRT/VTT/embedded text subtitles with FFmpeg and align to original PTS.',
        'transcript': 'Import explicit-time-base ASR JSON, preserving original text and translation.',
        'candidates': 'List candidate times, reasons, image paths and pending state by phase.',
        'focus': 'Add candidates for a specific gap using ORIGINAL timestamp seconds.',
        'extract': 'Export requested evidence PNGs with source-pixel hash checks.',
        'crop': 'Crop evidence without creating a new source-frame identity.',
        'record-view': 'Attest to an ACTUAL image tool call; cannot independently prove it.',
        'import-records': 'Merge structured operation steps/issues by ID; preserve history.',
        'status': 'Report computed, selected, recorded-viewed and unknown ranges separately.',
        'validate': 'Check references/hashes only; not proof of visual review.',
        'audit': 'Check interval/strict coverage, operations, discontinuities and bounded review validity.',
        'export': 'Reuse records to write review.json, frames.jsonl and report.md.'
    }.items():
        subs[name] = commands.add_parser(name, help=help_text)
        subs[name].add_argument('--work', required=True, type=Path, help='Dedicated review directory, one source video.')
    s = subs['scan']
    s.add_argument('video', type=Path)
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    s.add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    s.add_argument('--tile-size', type=int, default=32)
    s.add_argument('--pixel-threshold', type=int, default=8)
    s.add_argument('--checkpoint-frames', type=int, default=100)
    s.add_argument('--max-new-frames', type=int, help='Optional explicit compute budget, never a completion ceiling.')
    s = subs['select']
    s.add_argument('--mode', choices=['layered', 'coverage', 'changes'], default='layered',
                   help='layered proposes overview clusters; explicit coverage is exhaustive RGB-state mode.')
    s.add_argument('--anchor-seconds', type=float, default=5.0)
    s.add_argument('--global-threshold', type=float, default=2.0)
    s.add_argument('--local-threshold', type=float, default=0.8)
    s.add_argument('--min-changed-pixels', type=int, default=8)
    s.add_argument('--context-frames', type=int, default=1)
    s.add_argument('--pixel-threshold', type=int, help='Must equal scan threshold; change scan parameters in a new work directory.')
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
    group.add_argument('--frames', help='Comma-separated original 0-based frame ordinals.')
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    s = subs['crop']
    s.add_argument('--asset', required=True)
    s.add_argument('--box', required=True, help='x0,y0,x1,y1 in original image pixels, right/bottom exclusive.')
    s = subs['record-view']
    s.add_argument('--asset', required=True)
    s.add_argument('--actor', required=True)
    s.add_argument('--tool', required=True, choices=['view_image', 'read_image', 'image_tool', 'visible_attachment'])
    s.add_argument('--trace', required=True, help='Real image tool call/message reference, not a filename.')
    s.add_argument('--observation', required=True, help='What was actually visible, including unreadable regions.')
    subs['import-records'].add_argument('records', type=Path)
    subs['plan'].add_argument('--max-span', type=float, default=15.0, help='Local overview context duration; no total frame cap.')
    s = subs['sheet']
    s.add_argument('--frames', required=True)
    s.add_argument('--thumb-width', type=int, default=480)
    s.add_argument('--columns', type=int, default=4)
    s = subs['record-sheet-view']
    s.add_argument('--sheet', required=True)
    s.add_argument('--actor', required=True)
    s.add_argument('--trace', required=True)
    s.add_argument('--observations', required=True, type=Path, help='JSON object: only actually displayed asset IDs to observations.')
    subs['tracks'].add_argument('--ffprobe', default=os.environ.get('VOR_FFPROBE') or 'ffprobe')
    s = subs['subtitles']
    s.add_argument('source', type=Path)
    s.add_argument('--offset', type=float, default=0.0, help='original_video_time = subtitle_time + offset')
    s.add_argument('--language', default='und')
    s.add_argument('--stream', type=int, default=0, help='Subtitle s:N ordinal; text tracks only.')
    s.add_argument('--ffmpeg', default=os.environ.get('VOR_FFMPEG') or 'ffmpeg')
    subs['transcript'].add_argument('source', type=Path)
    subs['validate'].add_argument('--require-coverage', action='store_true',
                                  help='Require the selected mode coverage, continuity and a current recorded independent review.')
    subs['validate'].add_argument('--mode', choices=['layered','strict'])
    subs['audit'].add_argument('--mode', choices=['layered','strict'], help='Default: saved work mode; old work retains strict.')
    subs['audit'].add_argument('--queue', action='store_true', help='Add suggested gap frames to candidates without decoding or marking views.')
    subs['audit'].add_argument('--summary', action='store_true', help='Print counts and review status; omit large finding/state lists.')
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
                result = validate(conn, args.work, args.require_coverage, args.mode)
            elif command == 'audit':
                result = audit_omissions(conn, args.work, queue=args.queue, mode=args.mode)
                if args.summary:
                    result = {key: result[key] for key in ['snapshot', 'summary', 'records_ready_for_omission_review',
                              'omission_review', 'review_gate_passed_recorded', 'semantic_completeness_proven', 'assurance']}
            elif command == 'export':
                result = export_records(conn, args.work)
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
        print(dump({'error': str(exc), 'type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
