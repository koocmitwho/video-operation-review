"""Contact sheets are source-image compositions with explicit overview viewing granularity."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from vor_store import asset_path, dump, now, require_asset, sha256


def make_sheet(conn,work,frames,thumb_width=480,columns=4):
    if thumb_width<64 or columns<1: raise ValueError('Sheet width must be >=64 and columns positive.')
    frames=sorted(set(frames))
    if not frames: raise ValueError('Provide extracted source frames.')
    panels=[]
    for n in frames:
        asset,path=require_asset(conn,work,f'f{n:09d}')
        with Image.open(path) as im:
            size=(min(thumb_width,im.width),round(im.height*min(thumb_width,im.width)/im.width))
            panels.append((dict(asset),path,size))
    cell_h=max(p[2][1] for p in panels)+28
    columns=min(columns,len(panels))
    canvas=Image.new('RGB',(columns*thumb_width,((len(panels)+columns-1)//columns)*cell_h),'#10151c')
    draw=ImageDraw.Draw(canvas); members=[]
    for i,(asset,path,size) in enumerate(panels):
        x=(i%columns)*thumb_width; y=(i//columns)*cell_h
        with Image.open(path) as im: canvas.paste(im.resize(size),(x,y+28))
        time=conn.execute('SELECT time_s FROM frames WHERE frame_no=?',(asset['frame_no'],)).fetchone()[0]
        draw.text((x+4,y+5),f"Frame {asset['frame_no']} | PTS {time}",fill='white')
        members.append(dict(asset_id=asset['id'],frame_no=asset['frame_no'],source_sha256=asset['sha256'],
                            box=[x,y+28,x+size[0],y+28+size[1]],display_size=list(size)))
    key=hashlib.sha256(dump([members,thumb_width,columns]).encode()).hexdigest()[:20]
    ident='sheet-'+key; rel=f'evidence/{ident}.png'; path=asset_path(work,rel)
    if conn.execute('SELECT 1 FROM sheets WHERE id=?',(ident,)).fetchone():
        record=json.loads(conn.execute('SELECT payload FROM sheets WHERE id=?',(ident,)).fetchone()[0])
        if not path.is_file() or sha256(path)!=record['sha256']: raise ValueError('Existing sheet changed or missing.')
    else:
        canvas.save(path)
        record=dict(id=ident,path=rel,sha256=sha256(path),members=members,granularity='overview',created=now())
        with conn: conn.execute('INSERT INTO sheets VALUES (?,?)',(ident,dump(record)))
    return dict(record,absolute_path=str(path.resolve()))


def record_sheet_view(conn,work,ident,actor,trace,observations):
    row=conn.execute('SELECT payload FROM sheets WHERE id=?',(ident,)).fetchone()
    if row is None: raise ValueError('Unknown sheet.')
    record=json.loads(row[0]); path=asset_path(work,record['path'])
    if not path.is_file() or sha256(path)!=record['sha256']: raise ValueError('Sheet missing or changed.')
    if not actor.strip() or not trace.strip() or not isinstance(observations,dict) or not observations:
        raise ValueError('Actual call and per-visible-panel observations required.')
    members={m['asset_id']:m for m in record['members']}
    if not set(observations)<=set(members): raise ValueError('Observation references panel not in sheet.')
    with conn:
        for ref,observation in observations.items():
            if not isinstance(observation,str) or not observation.strip(): raise ValueError('Provide each visible panel observation.')
            asset,_=require_asset(conn,work,ref)
            if asset['sha256']!=members[ref]['source_sha256']: raise ValueError('Sheet source changed.')
            conn.execute('INSERT INTO views(asset_id,frame_no,actor,tool,trace_ref,observation,asset_sha256,created,presentation,sheet_id) '
                         'VALUES (?,?,?,?,?,?,?,?,?,?)',(ref,asset['frame_no'],actor,'image_tool',trace,observation,asset['sha256'],now(),'overview',ident))
    return dict(sheet=ident,recorded_panels=len(observations),granularity='overview',actual_attention_independently_verified=False)
