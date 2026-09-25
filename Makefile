.PHONY: test demo encoders

test:
	python3 -m unittest discover -s tests -v

demo:
	python3 run.py examples/video_plan.json examples/candidates.json --out demo_run

encoders:
	./tools/probe_encoders.sh
