#!/usr/bin/env python3
"""Continuity-first, provider-agnostic presenter-video pipeline."""
from __future__ import annotations
import argparse, hashlib, html, json, pathlib, platform, shutil, sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def read(p): return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def write(p, x):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(x, indent=2, sort_keys=True)+"\n", encoding="utf-8")
def frame(s, fps): return round(float(s)*fps)
def sha(p):
    p = pathlib.Path(p)
    if not p.is_file(): return None
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1048576), b""): h.update(b)
    return h.hexdigest()

def validate(plan):
    e=[]; fps=plan.get("frameRate")
    if plan.get("schema") != 1: e.append("schema must be 1")
    if fps not in (24,25,30): e.append("frameRate must be 24, 25, or 30")
    if plan.get("resolution") != [1080,1350]: e.append("resolution must be [1080, 1350]")
    for k in ("presenterStill","audio","script","background"):
        if not plan.get("inputs",{}).get(k): e.append(f"inputs.{k} is required")
    if not plan.get("presenterProfile",{}).get("faceTarget") or not plan.get("presenterProfile",{}).get("despill"): e.append("presenter profile requires faceTarget and despill")
    chunks=plan.get("chunks",[]); prior=None; ids=set()
    if not chunks: e.append("at least one chunk is required")
    for i,c in enumerate(chunks):
        if c.get("id") in ids: e.append(f"chunks[{i}] duplicate id")
        ids.add(c.get("id")); start,end=c.get("start"),c.get("end")
        if not all(k in c for k in ("id","start","end","line")): e.append(f"chunks[{i}] missing required fields"); continue
        if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or end<=start: e.append(f"chunks[{i}] invalid range"); continue
        if prior is not None and abs(start-prior)>1e-6: e.append(f"chunks[{i}] must begin at previous end")
        if fps and (frame(start,fps)/fps != start or frame(end,fps)/fps != end): e.append(f"chunks[{i}] not frame aligned")
        if c.get("overlap",0)<1: e.append(f"chunks[{i}] requires >=1 second overlap")
        prior=end
    return e

def timeline(plan):
    fps=plan["frameRate"]; chunks=[]; joins=[]
    for i,c in enumerate(plan["chunks"]):
        start,end=frame(c["start"],fps),frame(c["end"],fps); overlap=frame(c.get("overlap",2),fps)
        chunks.append({**c,"startFrame":start,"endFrame":end,"generationStartFrame":max(0,start-overlap),"generationEndFrame":end+overlap})
        if i: joins.append({"id":f"{plan['chunks'][i-1]['id']}--{c['id']}","atFrame":start,"transitionFrames":min(8,max(3,overlap//2)),"strategy":"match-or-bridge","reviewRequired":True})
    return {"schema":1,"generatedAt":now(),"audioIsMasterClock":True,"frameRate":fps,"resolution":plan["resolution"],"chunks":chunks,"joins":joins,"supers":plan.get("supers",[])}

def score(c):
    m=c.get("metrics",{}); limits={"lipLagMs":45,"faceDelta":.08,"poseDelta":.12,"handDelta":.18,"greenSpillPercent":1.5}; weights={"lipLagMs":.35,"faceDelta":.2,"poseDelta":.2,"handDelta":.15,"greenSpillPercent":.1}
    return round(sum(min(1,abs(float(m.get(k,limits[k])))/limits[k])*weights[k] for k in limits),4)

def select(tl, candidates):
    by={}
    for c in candidates.get("candidates",[]): by.setdefault(c.get("chunkId"),[]).append(c)
    selected={}; rejected=[]
    for chunk in tl["chunks"]:
        options=sorted(((score(c),c) for c in by.get(chunk["id"],[])),key=lambda x:x[0])
        if not options: rejected.append({"chunkId":chunk["id"],"reason":"no provider candidates"}); continue
        s,c=options[0]; selected[chunk["id"]]={"candidateId":c.get("id"),"path":c.get("path"),"score":s,"metrics":c.get("metrics",{})}
        rejected += [{"chunkId":chunk["id"],"candidateId":x.get("id"),"reason":"lower ranked"} for _,x in options[1:]]
    return {"schema":1,"generatedAt":now(),"selected":selected,"rejected":rejected}

def join_plan(tl, selection):
    out=[]; selected=selection.get("selected",{})
    for j in tl["joins"]:
        a,b=j["id"].split("--"); ma,mb=selected.get(a,{}).get("metrics",{}),selected.get(b,{}).get("metrics",{})
        d={k:abs(float(ma.get(k,1))-float(mb.get(k,1))) for k in ("faceDelta","poseDelta","handDelta")}; risk=round(.3*d["faceDelta"]+.35*d["poseDelta"]+.35*d["handDelta"],4)
        strategy="direct-cut" if risk<=.06 else "optical-flow-bridge" if risk<=.2 else "regenerate-bridge"
        out.append({**j,"deltas":d,"risk":risk,"strategy":strategy,"status":"needs-regeneration" if risk>.2 else "needs-review"})
    return {"schema":1,"generatedAt":now(),"joins":out}

def qc(plan, tl, selection, joins):
    errors=validate(plan); limit=float(plan.get("qc",{}).get("maxJoinRisk",.2)); checks={"manifestValid":not errors,"audioIsMasterClock":tl.get("audioIsMasterClock") is True,"candidatesSelected":len(selection.get("selected",{}))==len(plan["chunks"]),"joinRiskPassed":all(j["risk"]<=limit for j in joins.get("joins",[])),"reviewRequired":all(j.get("reviewRequired") for j in joins.get("joins",[]))}
    blockers=errors+(["candidate selection incomplete"] if not checks["candidatesSelected"] else [])+(["join risk exceeds threshold"] if not checks["joinRiskPassed"] else [])
    return {"schema":1,"generatedAt":now(),"status":"PASS" if not blockers else "BLOCKED","checks":checks,"blockers":blockers,"delivery":"allowed" if not blockers else "blocked"}

def probe(): return {"schema":1,"platform":platform.platform(),"intermediate":"ProRes 422/4444","delivery":["H.264","HEVC"],"status":"must-probe-with-avfoundation","policy":"fail closed if no encoder is available"}
def review(joins):
    rows="".join(f"<tr><td>{html.escape(j['id'])}</td><td>{j['risk']:.3f}</td><td>{html.escape(j['strategy'])}</td><td>{html.escape(j['status'])}</td></tr>" for j in joins["joins"])
    return f"<!doctype html><title>Join review</title><style>body{{font-family:system-ui;margin:3rem}}td,th{{padding:.5rem;border:1px solid #ddd}}</style><h1>Frame-by-frame join review</h1><table><tr><th>Join</th><th>Risk</th><th>Bridge</th><th>Status</th></tr>{rows}</table>"
def provenance(manifest, plan): return {"schema":1,"generatedAt":now(),"manifest":{"path":str(manifest),"sha256":sha(manifest)},"inputs":{k:{"path":v,"sha256":sha(manifest.parent/v)} for k,v in plan.get("inputs",{}).items()},"platform":platform.platform()}

def demo(out):
    out=pathlib.Path(out); out.mkdir(parents=True,exist_ok=True); target=out/"video_plan.json"; shutil.copyfile(ROOT/"examples"/"video_plan.json",target); plan=read(target); tl=timeline(plan)
    candidates={"candidates":[{"id":"c1-a","chunkId":"c1","path":"provider/c1-a.mov","metrics":{"lipLagMs":12,"faceDelta":.02,"poseDelta":.03,"handDelta":.04,"greenSpillPercent":.4}},{"id":"c2-a","chunkId":"c2","path":"provider/c2-a.mov","metrics":{"lipLagMs":14,"faceDelta":.03,"poseDelta":.04,"handDelta":.05,"greenSpillPercent":.5}}]}; sel=select(tl,candidates); joins=join_plan(tl,sel)
    for n,v in {"timeline.json":tl,"candidates.json":candidates,"selection.json":sel,"joins.json":joins,"qc_report.json":qc(plan,tl,sel,joins),"provenance.json":provenance(target,plan),"encoder_probe.json":probe()}.items():write(out/n,v)
    (out/"join_review.html").write_text(review(joins),encoding="utf-8"); print(f"Demo completed: {out}")

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True); s.add_parser("encoders"); d=s.add_parser("demo");d.add_argument("--out",required=True); v=s.add_parser("validate");v.add_argument("manifest"); t=s.add_parser("timeline");t.add_argument("manifest");t.add_argument("--out",required=True); c=s.add_parser("select");c.add_argument("timeline");c.add_argument("candidates");c.add_argument("--out",required=True); j=s.add_parser("joins");j.add_argument("timeline");j.add_argument("selection");j.add_argument("--out",required=True); q=s.add_parser("qc");q.add_argument("manifest");q.add_argument("timeline");q.add_argument("selection");q.add_argument("joins");q.add_argument("--out",required=True); r=s.add_parser("review");r.add_argument("joins");r.add_argument("--out",required=True); a=p.parse_args()
    if a.cmd=="demo":demo(a.out);return
    if a.cmd=="encoders":print(json.dumps(probe(),indent=2));return
    if a.cmd=="validate":
        errors=validate(read(a.manifest));print("VALID" if not errors else "INVALID\n"+"\n".join("- "+x for x in errors));sys.exit(bool(errors))
    if a.cmd=="timeline":result=timeline(read(a.manifest))
    elif a.cmd=="select":result=select(read(a.timeline),read(a.candidates))
    elif a.cmd=="joins":result=join_plan(read(a.timeline),read(a.selection))
    elif a.cmd=="qc":result=qc(read(a.manifest),read(a.timeline),read(a.selection),read(a.joins))
    else:pathlib.Path(a.out).write_text(review(read(a.joins)),encoding="utf-8");return
    write(a.out,result)
if __name__=="__main__":main()
