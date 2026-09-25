import json, pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PipelineTests(unittest.TestCase):
 def test_demo_passes(self):
  with tempfile.TemporaryDirectory() as d:
   out=pathlib.Path(d)/"run";subprocess.run(["python3","pipeline.py","demo","--out",str(out)],cwd=ROOT,check=True)
   self.assertEqual(json.loads((out/"qc_report.json").read_text())["status"],"PASS")
 def test_gap_rejected(self):
  x=json.loads((ROOT/"examples/video_plan.json").read_text());x["chunks"][1]["start"]=8.5
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/"bad.json";p.write_text(json.dumps(x));self.assertNotEqual(subprocess.run(["python3","pipeline.py","validate",str(p)],cwd=ROOT).returncode,0)
if __name__=="__main__":unittest.main()
