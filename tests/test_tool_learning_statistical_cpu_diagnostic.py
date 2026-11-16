"""Tiny POSIX sampling tests; no full replay or real model."""
import inspect
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from evaluation.tool_learning_continuation_diagnostic import ExclusiveObserver
from evaluation.tool_learning_statistical_cpu_diagnostic import CPUSampler

SUPPORTED=all(hasattr(signal,n)for n in ('SIGPROF','ITIMER_PROF','getitimer','setitimer','pthread_sigmask','sigpending','sigwait'))

class StatisticalCPUDiagnosticTests(unittest.TestCase):
    def test_handler_counts_full_code_stack_without_local_values_and_bounds_unique_stacks(self):
        stages=ExclusiveObserver();sampler=CPUSampler(stages,max_stacks=1);secret_local='DO_NOT_CAPTURE_THIS_LOCAL_VALUE'
        self.assertEqual(sampler.interval,.02)
        sampler.active=True;sampler.handler(0,inspect.currentframe())
        sampler.handler(0,inspect.currentframe());sampler.active=False
        report=sampler.report();self.assertEqual(report['samples'],1);self.assertEqual(report['losses']['distinct_stack_limit'],1)
        self.assertGreater(report['max_observed_stack_depth'],1);self.assertNotIn(secret_local,json.dumps(report))
        frames=report['stages'][0]['stacks'][0]['frames'];self.assertEqual(len(frames),report['max_observed_stack_depth'])
    def test_overlong_stack_and_reentrant_handler_are_explicit_losses(self):
        sampler=CPUSampler(ExclusiveObserver(),max_frames=1);sampler.active=True
        sampler.handler(0,inspect.currentframe());sampler.handling=True;sampler.handler(0,inspect.currentframe());sampler.active=False
        self.assertEqual(sampler.losses['overlong_stack'],1);self.assertEqual(sampler.losses['reentrant'],1);self.assertEqual(sampler.samples,0)
        capped=CPUSampler(ExclusiveObserver(),max_codes=0);capped.active=True;capped.handler(0,inspect.currentframe());capped.active=False
        self.assertGreater(capped.losses['code_catalog_limit_frames'],0);self.assertIn('0',capped.report()['code_catalog'])
    @unittest.skipUnless(SUPPORTED,'required POSIX signals unavailable')
    def test_existing_handler_or_timer_is_never_stolen(self):
        with patch.object(signal,'getsignal',return_value=lambda a,b:None),patch.object(signal,'getitimer',return_value=(0.,0.)),patch.object(signal,'setitimer')as changed:
            sampler=CPUSampler(ExclusiveObserver());self.assertFalse(sampler.install());changed.assert_not_called()
        with patch.object(signal,'getsignal',return_value=signal.SIG_DFL),patch.object(signal,'getitimer',return_value=(1.,.005)),patch.object(signal,'setitimer')as changed:
            sampler=CPUSampler(ExclusiveObserver());self.assertFalse(sampler.install());changed.assert_not_called()
    @unittest.skipUnless(SUPPORTED,'required POSIX signals unavailable')
    def test_cleanup_restores_default_handler_and_zero_timer_without_late_signal_killing_process(self):
        script="""import signal
from evaluation.tool_learning_continuation_diagnostic import ExclusiveObserver
from evaluation.tool_learning_statistical_cpu_diagnostic import CPUSampler
old=signal.getsignal(signal.SIGPROF)
for i in range(20):
 s=CPUSampler(ExclusiveObserver(),interval=.0005)
 try:
  with s.running():
   for n in range(20000):pass
   if i%2:raise RuntimeError('synthetic cleanup')
 except RuntimeError:pass
 assert signal.getsignal(signal.SIGPROF)==old
 assert signal.getitimer(signal.ITIMER_PROF)==(0.,0.)
print('restored')
"""
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('restored',result.stdout)
    @unittest.skipUnless(SUPPORTED,'required POSIX signals unavailable')
    def test_actual_isolated_registration_keeps_original_validator_and_strong_receipts(self):
        from tests.test_tool_learning_certified_input import CertifiedInputTests
        from digital_life.infrastructure.persistence.tool_learning_store import ToolLearningStore
        from digital_life.infrastructure.persistence.sqlite_store import managed_database
        case=CertifiedInputTests();case.setUp();original=ToolLearningStore.validate_ref;sampler=CPUSampler(ExclusiveObserver(),interval=.0005)
        try:
            with sampler.running(),case.meter().installed(case.s),case.e.owners.source.verification_boundary():
                self.assertIs(ToolLearningStore.validate_ref,original);self.assertTrue(managed_database(case.s.db).known_read_environment());case.register('/sampling-test')
            self.assertEqual(case.s._input_certificate_stats['strong_material_accepted'],1);self.assertEqual(case.s._input_certificate_stats['strong_material_committed'],1)
            self.assertGreater(sampler.samples,0);self.assertIs(ToolLearningStore.validate_ref,original)
            self.assertFalse(sampler.report()['sqlite_trace_or_row_observer_installed'])
        finally:case.doCleanups();sampler.close()
    def test_main_preserves_scale_arguments_and_saves_setup_failure(self):
        from evaluation import tool_learning_statistical_cpu_diagnostic as tool
        from evaluation import tool_learning_continuation_diagnostic as diagnostic
        forwarded=[]
        def failed(argv):forwarded.extend(argv);raise RuntimeError('setup failure')
        with tempfile.TemporaryDirectory()as directory,patch.object(diagnostic,'main',side_effect=failed):
            with self.assertRaisesRegex(RuntimeError,'setup failure'):tool.main(['--source','synthetic','--output',directory,'--continuation-turns','2'])
            result=json.loads((Path(directory)/'statistical-cpu-samples.json').read_text());self.assertFalse(result['installed']);self.assertEqual(result['main_error_type'],'RuntimeError')
        self.assertEqual(forwarded,['--counters-only','--source','synthetic','--output',directory,'--continuation-turns','2'])
