"""AdsPulse demo API: synthetic campaign reporting with reliable partner sync."""
from __future__ import annotations
import json
import os
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = os.environ.get('DB_PATH', str(Path(__file__).resolve().parent.parent / 'adspulse.db'))
SYNC_LOCK = Lock()
app = FastAPI(title='AdsPulse API', version='1.0.0', description='Sample marketing analytics with simulated partner integrations')
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get('CORS_ORIGINS', 'http://localhost:5173,http://localhost:8080').split(','), allow_methods=['GET','POST'], allow_headers=['*'])

def conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, name TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS daily_metrics (campaign_id TEXT NOT NULL, day TEXT NOT NULL, impressions INTEGER NOT NULL, clicks INTEGER NOT NULL, conversions INTEGER NOT NULL, spend REAL NOT NULL, revenue REAL NOT NULL, PRIMARY KEY(campaign_id,day));
        CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT, source TEXT NOT NULL, status TEXT NOT NULL, rows_synced INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
        ''')

def now(): return datetime.now(timezone.utc).isoformat()
def log(db, level, message): db.execute('INSERT INTO events(at,level,message) VALUES(?,?,?)',(now(),level,message))

SOURCES = ['Search Partner', 'Social Partner', 'Video Partner']
CAMPAIGNS = [
 ('s1','Brand Search','Search','Active','Search Partner'),('s2','Spring Shopping','Search','Active','Search Partner'),
 ('s3','Remarketing','Search','Paused','Search Partner'),('m1','New Audience','Social','Active','Social Partner'),
 ('m2','Mobile Acquisition','Social','Active','Social Partner'),('v1','Creator Launch','Video','Active','Video Partner'),
 ('v2','Product Showcase','Video','Active','Video Partner')]

def sample_partner_feed(source: str, days: int = 30, simulate_failure: bool = False):
    """Deterministic stand-in for third-party APIs; replace this adapter with authorized provider APIs."""
    if source not in SOURCES: raise ValueError('Unknown provider')
    if simulate_failure: raise ConnectionError(f'{source} responded with simulated HTTP 503')
    records=[]
    for id_,name,channel,status,src in CAMPAIGNS:
        if src != source: continue
        for i in range(days):
            day=(datetime.now(timezone.utc).date()-timedelta(days=days-1-i)).isoformat()
            seed=sum(map(ord,id_))*1000+i*47
            r=random.Random(seed)
            impressions=r.randint(2500,16500)
            clicks=round(impressions*r.uniform(.016,.075))
            conversions=round(clicks*r.uniform(.025,.15))
            spend=round(clicks*r.uniform(.38,2.6),2)
            revenue=round(conversions*r.uniform(18,92),2)
            records.append((id_,day,impressions,clicks,conversions,spend,revenue))
    return records

def sync_source(source: str, simulate_failure=False, max_attempts=3, wait=lambda _:None):
    """Idempotent upsert with bounded retries, transparent logging, and run history."""
    if source not in SOURCES: raise ValueError('Unknown provider')
    with SYNC_LOCK:
        with conn() as db:
            started=now()
            run_id=db.execute('INSERT INTO sync_runs(started_at,source,status) VALUES(?,?,?)',(started,source,'running')).lastrowid
            db.commit()
        for attempt in range(1,max_attempts+1):
            try:
                records=sample_partner_feed(source, simulate_failure=simulate_failure)
                with conn() as db:
                    db.executemany('INSERT INTO campaigns VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,channel=excluded.channel,status=excluded.status,source=excluded.source', [x for x in CAMPAIGNS if x[4]==source])
                    db.executemany('INSERT INTO daily_metrics VALUES(?,?,?,?,?,?,?) ON CONFLICT(campaign_id,day) DO UPDATE SET impressions=excluded.impressions,clicks=excluded.clicks,conversions=excluded.conversions,spend=excluded.spend,revenue=excluded.revenue',records)
                    db.execute('UPDATE sync_runs SET finished_at=?,status=?,rows_synced=?,attempts=?,error=NULL WHERE id=?',(now(),'success',len(records),attempt,run_id))
                    log(db,'success',f'{source}: synchronized {len(records)} rows on attempt {attempt}')
                return {'source':source,'status':'success','rows_synced':len(records),'attempts':attempt,'run_id':run_id}
            except (ConnectionError, TimeoutError, ValueError) as exc:
                with conn() as db:
                    log(db,'warning',f'{source}: attempt {attempt}/{max_attempts} failed: {exc}')
                if attempt < max_attempts: wait(min(2**(attempt-1),4))
                else:
                    with conn() as db:
                        db.execute('UPDATE sync_runs SET finished_at=?,status=?,attempts=?,error=? WHERE id=?',(now(),'failed',attempt,str(exc),run_id))
                    return {'source':source,'status':'failed','rows_synced':0,'attempts':attempt,'run_id':run_id,'error':str(exc)}

class SyncRequest(BaseModel):
    source: Literal['Search Partner','Social Partner','Video Partner','All'] = 'All'
    simulate_failure: bool = False

@app.on_event('startup')
def startup():
    init_db()
    with conn() as db:
        count=db.execute('SELECT count(*) FROM campaigns').fetchone()[0]
    if count == 0:
        for source in SOURCES: sync_source(source)

@app.get('/api/health')
def health(): return {'status':'ok','time':now(),'mode':'synthetic demo data'}

@app.post('/api/sync')
def sync(payload: SyncRequest):
    targets=SOURCES if payload.source=='All' else [payload.source]
    results=[sync_source(s,simulate_failure=payload.simulate_failure) for s in targets]
    return {'runs':results, 'status':'success' if all(x['status']=='success' for x in results) else 'partial_failure'}

@app.get('/api/campaigns')
def campaigns(channel: str = 'All', search: str = '', days: int = Query(30,ge=1,le=90)):
    cutoff=(datetime.now(timezone.utc).date()-timedelta(days=days-1)).isoformat()
    with conn() as db:
        rows=db.execute('''SELECT c.*,COALESCE(SUM(m.impressions),0) impressions,COALESCE(SUM(m.clicks),0) clicks,COALESCE(SUM(m.conversions),0) conversions,ROUND(COALESCE(SUM(m.spend),0),2) spend,ROUND(COALESCE(SUM(m.revenue),0),2) revenue
            FROM campaigns c LEFT JOIN daily_metrics m ON m.campaign_id=c.id AND m.day>=?
            WHERE (?='All' OR c.channel=?) AND lower(c.name) LIKE ? GROUP BY c.id ORDER BY spend DESC''', (cutoff,channel,channel,'%'+search.lower()+'%')).fetchall()
    return [{**dict(r),'ctr':round(100*r['clicks']/r['impressions'],2) if r['impressions'] else 0,'roas':round(r['revenue']/r['spend'],2) if r['spend'] else 0} for r in rows]

@app.get('/api/summary')
def summary(channel: str = 'All', days: int = Query(30,ge=1,le=90)):
    rows=campaigns(channel=channel,days=days)
    totals={k:round(sum(r[k] for r in rows),2) for k in ['impressions','clicks','conversions','spend','revenue']}
    totals['ctr']=round(100*totals['clicks']/totals['impressions'],2) if totals['impressions'] else 0
    totals['roas']=round(totals['revenue']/totals['spend'],2) if totals['spend'] else 0
    totals['campaigns']=len(rows)
    return totals

@app.get('/api/trends')
def trends(channel: str = 'All', days: int = Query(30,ge=1,le=90)):
    cutoff=(datetime.now(timezone.utc).date()-timedelta(days=days-1)).isoformat()
    with conn() as db:
        rows=db.execute('''SELECT m.day,ROUND(SUM(m.spend),2) spend,ROUND(SUM(m.revenue),2) revenue,SUM(m.clicks) clicks,SUM(m.conversions) conversions FROM daily_metrics m JOIN campaigns c ON c.id=m.campaign_id WHERE m.day>=? AND (?='All' OR c.channel=?) GROUP BY m.day ORDER BY m.day''',(cutoff,channel,channel)).fetchall()
    return [dict(r) for r in rows]

@app.get('/api/activity')
def activity():
    with conn() as db:
        runs=[dict(x) for x in db.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 12')]
        events=[dict(x) for x in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 20')]
    return {'runs':runs,'events':events}
