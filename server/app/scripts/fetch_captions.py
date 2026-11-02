"""Fetch the captions of saved YouTube videos that have none, from this machine.

YouTube refuses caption requests from cloud servers (PLAN v11), so a pile imported on the
server has titles only. This runs where captions work (a home connection), stores them as
the save's transcript, as a normal save would, and calls no model. The prep sheet (S12)
reads them from there.

Run: python -m uv run python -m app.scripts.fetch_captions <user_id> [thread_id ...]
With thread ids, only the videos in those goals; without, all of the person's videos.
"""

import sys
import time

from sqlalchemy import exists, select

from app.db.models import Save, Snapshot, ThreadSave
from app.db.session import session_factory
from app.ingest.gather import CaptionsUnavailable, _captions, transcript_text
from app.ingest.urls import youtube_id

PAUSE_S = 2.0  # one request at a time, so YouTube doesn't block this machine too


user_id, thread_ids = sys.argv[1], sys.argv[2:]
with session_factory()() as db:
    has_captions = exists().where(Snapshot.save_id == Save.id, Snapshot.kind == "transcript")
    query = select(Save).where(
        Save.user_id == user_id,
        Save.platform == "youtube",
        Save.visibility == "normal",
        ~has_captions,
    )
    if thread_ids:
        query = query.where(
            Save.id.in_(select(ThreadSave.save_id).where(ThreadSave.thread_id.in_(thread_ids)))
        )
    saves = db.scalars(query).all()
    got = none = blocked = 0
    for n, save in enumerate(saves, 1):
        vid = youtube_id(save.url or "")
        if not vid:
            continue
        try:
            segments = _captions(vid)
        except CaptionsUnavailable as exc:
            if exc.blocked:
                blocked += 1
                print(f"{n}/{len(saves)} {vid}: YouTube refused; stopping to stay unblocked.")
                break
            none += 1
            print(f"{n}/{len(saves)} {vid}: no captions")
            continue
        watch = f"https://www.youtube.com/watch?v={vid}"
        db.add(
            Snapshot(
                save_id=save.id,
                kind="transcript",
                source_url=watch,
                text=transcript_text(segments),
                meta={"segments": segments, "source": "captions", "fetched_from": "home"},
            )
        )
        db.commit()
        got += 1
        print(f"{n}/{len(saves)} {vid}: {len(segments)} lines")
        time.sleep(PAUSE_S)
    print(f"Captions stored for {got} videos; {none} have none; {blocked} refused.")
