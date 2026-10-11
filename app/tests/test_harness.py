"""Offline harness regression tests: no provider calls or board decisions."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gtm import cli, config, workflow
from gtm.contract import ORDER, OUTPUTS, brief_description, parse_brief
from gtm.roles import publish
from gtm.run import Run

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("campaign", ROOT / "harness" / "campaign.py")
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(config, "RUNS_DIR", Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.run = Run("TEST-1")
        self.brief = {"brand_url": "https://example.org", "niche": "gardening", "audience": "gardeners", "goal": "newsletter", "platforms": "youtube"}
        self.run.write("brief.json", self.brief)

    def package(self):
        self.run.write("qa.json", {"passed": True, "final_version": 1})
        self.run.write("script_v1.json", {"hook": "Grow herbs"})
        self.run.path("video_v1.mp4").write_bytes(b"fixture media")
        self.run.write("publish.json", {"version": 1, "status": "awaiting_approval", "artifact_hash": publish.fingerprint(self.run, 1)})

    def test_structured_brief_round_trip(self):
        parsed = parse_brief(brief_description(self.brief))
        self.assertEqual(parsed["audience"], "gardeners")
        self.assertEqual(parsed["brand"], "example.org")
        self.assertEqual(parsed["platforms"], ["youtube"])

    def test_harness_producer_matches_worker(self):
        args = SimpleNamespace(brand="https://example.org", niche="gardening", audience="gardeners", goal="newsletter", platforms="youtube", voice="plain", competitors="none", cadence="weekly", brief="a custom note")
        parsed = cli._brief_from({"description": campaign.brief_md(args)})
        self.assertEqual(parsed["goal"], args.goal)
        self.assertEqual(parsed["notes"], args.brief)

    def test_missing_brief_does_not_use_tinyfish(self):
        with self.assertRaisesRegex(ValueError, "brand_url"):
            parse_brief("Please do marketing")

    def test_existing_markdown_brief(self):
        value = parse_brief("brand_url: https://example.org\nniche: gardening\n- **Audience:** gardeners\n- **Goal:** newsletter")
        self.assertEqual(value["audience"], "gardeners")

    def test_missing_prerequisite_blocks_before_worker(self):
        worker = Mock()
        with self.assertRaises(workflow.StageBlocked):
            workflow.execute(self.run, "analysis", worker)
        worker.assert_not_called()
        self.assertEqual(self.run.read("workflow.json")["status"], "blocked")

    def test_done_stage_is_not_reexecuted(self):
        def research(run):
            run.write("evidence.json", {})
            return "researched"
        worker = Mock(side_effect=research)
        workflow.execute(self.run, "research", worker)
        workflow.execute(self.run, "research", worker)
        self.assertEqual(worker.call_count, 1)

    def test_failed_qa_cannot_finish_or_publish(self):
        for name in OUTPUTS["video"]:
            self.run.write(name, {})
        def qa(run):
            run.write("qa.json", {"passed": False})
            return "needs human"
        with self.assertRaises(workflow.StageBlocked):
            workflow.execute(self.run, "qa", qa)
        worker = Mock()
        with self.assertRaises(workflow.StageBlocked):
            workflow.execute(self.run, "publish", worker)
        worker.assert_not_called()

    def test_approval_required_before_learning(self):
        self.package()
        with self.assertRaisesRegex(workflow.StageBlocked, "Human approval"):
            workflow.execute(self.run, "learn", Mock())

    def test_stale_media_cannot_be_approved(self):
        self.package()
        self.run.path("video_v1.mp4").write_bytes(b"different media")
        with self.assertRaisesRegex(ValueError, "stale"):
            publish.run(self.run, approved=True)

    def test_local_approval_cannot_bypass_board(self):
        self.package()
        pkg = self.run.read("publish.json")
        self.run.write("publish.json", {**pkg, "approval_id": "ap-1"})
        with self.assertRaisesRegex(ValueError, "Paperclip"):
            publish.run(self.run, approved=True)

    def test_verified_approval_completes_package(self):
        self.package()
        pkg = self.run.read("publish.json")
        self.run.write("publish.json", {**pkg, "approval_id": "ap-1"})
        publish.run(self.run, approved=True, approval={"id": "ap-1", "status": "approved"})
        self.assertEqual(self.run.read("publish.json")["status"], "ready_to_publish")

    def test_changed_approved_media_blocks_learning(self):
        self.package()
        publish.run(self.run, approved=True)
        self.run.path("video_v1.mp4").write_bytes(b"replacement")
        worker = Mock()
        with self.assertRaisesRegex(workflow.StageBlocked, "changed"):
            workflow.execute(self.run, "learn", worker)
        worker.assert_not_called()

    def test_worker_recovers_pending_approval_without_duplicate(self):
        self.package()
        pc = Mock()
        pc.current_issue.return_value = {"id": "issue-1"}
        pc.campaign_id.return_value = self.run.id
        approval = {"id": "ap-1", "status": "pending", "payload": {"artifactHash": self.run.read("publish.json")["artifact_hash"]}}
        pc.request.side_effect = lambda method, path: [approval] if path.endswith("/approvals") else approval
        with patch("gtm.paperclip_agent.PaperclipRun.from_env", return_value=pc), patch.object(cli.report, "build"):
            self.assertEqual(cli._paperclip_agent("publish"), 0)
            self.assertEqual(cli._paperclip_agent("publish"), 0)
        pc.request_approval.assert_not_called()
        pc.done.assert_not_called()
        self.assertEqual(self.run.read("publish.json")["approval_id"], "ap-1")

    def test_offline_lifecycle_stops_then_completes_after_approval(self):
        self.package()
        def worker_for(role):
            def worker(run):
                for name in OUTPUTS[role]:
                    if not run.exists(name):
                        run.write(name, {})
                return role
            return worker
        for role in ORDER[:-1]:
            workflow.execute(self.run, role, worker_for(role))
        self.assertEqual(self.run.read("workflow.json")["status"], "awaiting_approval")
        publish.run(self.run, approved=True)
        workflow.record(self.run, "publish", "done")
        workflow.execute(self.run, "learn", worker_for("learn"))
        self.assertEqual(self.run.read("workflow.json")["status"], "complete")

    def test_run_id_cannot_escape_artifact_root(self):
        with self.assertRaises(ValueError):
            Run("../escape")

    def test_campaign_issues_follow_shared_order(self):
        args = SimpleNamespace(brand="https://example.org", niche="gardening", audience="gardeners", goal="newsletter", platforms="youtube", voice="plain", competitors="", cadence="weekly", brief="", mode="pipeline")
        calls = []
        def create(method, path, body):
            calls.append(body)
            return {"id": f"id-{len(calls)}", "identifier": f"TEST-{len(calls)}"}
        with patch.object(campaign, "call", side_effect=create), patch.object(campaign, "cmd_doctor"), patch.object(campaign, "A", {r: r for r in ORDER}), patch.object(campaign, "STATE", {"projectId": "p", "goalId": "g", "publicUrl": "http://test"}):
            campaign.cmd_new(args)
        self.assertEqual([b["assigneeAgentId"] for b in calls[1:]], ORDER)
        self.assertEqual(calls[1]["blockedByIssueIds"], [])
        for i in range(2, len(calls)):
            self.assertEqual(calls[i]["blockedByIssueIds"], [f"id-{i}"])

    def test_worker_reconciles_verified_approval(self):
        self.package()
        pc = Mock()
        pc.current_issue.return_value = {"id": "issue-1"}
        pc.campaign_id.return_value = self.run.id
        approval = {"id": "ap-1", "status": "approved", "payload": {"artifactHash": self.run.read("publish.json")["artifact_hash"]}}
        pc.request.side_effect = lambda method, path: [approval] if path.endswith("/approvals") else approval
        with patch("gtm.paperclip_agent.PaperclipRun.from_env", return_value=pc), patch.object(cli.report, "build"):
            self.assertEqual(cli._paperclip_agent("publish"), 0)
        self.assertEqual(self.run.read("workflow.json")["stages"]["publish"]["status"], "done")
        pc.done.assert_called_once()

    def test_worker_blocks_rejected_approval(self):
        self.package()
        pc = Mock()
        pc.current_issue.return_value = {"id": "issue-1"}
        pc.campaign_id.return_value = self.run.id
        approval = {"id": "ap-1", "status": "rejected", "payload": {"artifactHash": self.run.read("publish.json")["artifact_hash"]}}
        pc.request.side_effect = lambda method, path: [approval] if path.endswith("/approvals") else approval
        with patch("gtm.paperclip_agent.PaperclipRun.from_env", return_value=pc), patch.object(cli.report, "build"):
            self.assertEqual(cli._paperclip_agent("publish"), 1)
        pc.done.assert_not_called()
        pc.blocked.assert_called_once()

    def test_only_one_worker_can_lock_campaign(self):
        with self.run.exclusive():
            with self.assertRaisesRegex(RuntimeError, "active worker"):
                with Run(self.run.id).exclusive():
                    self.fail("second worker entered")


if __name__ == "__main__":
    unittest.main()
