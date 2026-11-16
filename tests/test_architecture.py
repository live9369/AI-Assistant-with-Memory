"""Executable layer boundaries to keep directory structure from drifting."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
from digital_life.infrastructure.persistence.sqlite_store import PROJECT

class ArchitectureTests(unittest.TestCase):
    def imports(self,path):
        tree=ast.parse(path.read_text())
        return [node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module]+[alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names]
    def test_domain_has_no_application_infrastructure_or_legacy_dependencies(self):
        for path in (PROJECT/'digital_life/domain').glob('*.py'):
            for name in self.imports(path):
                self.assertFalse(name.startswith(('digital_life.application','digital_life.infrastructure','digital_life.entrypoints','primordial00','sqlite3','urllib')),str(path)+': '+name)
    def test_infrastructure_has_no_application_or_legacy_dependencies(self):
        for path in (PROJECT/'digital_life/infrastructure').rglob('*.py'):
            for name in self.imports(path): self.assertFalse(name.startswith(('digital_life.application','digital_life.entrypoints','primordial00')),str(path)+': '+name)
    def test_services_are_individually_maintainable(self):
        folder=PROJECT/'digital_life/application/services'
        for name in ('memory','personality','values','goals','habits','relationships','commitments','states','cognition','decisions','learning','identity','health'):
            self.assertTrue((folder/(name+'.py')).is_file(),name)
    def test_modern_system_imports_with_legacy_package_blocked(self):
        code='''import sys,importlib.abc
class NoLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='primordial00' or fullname.startswith('primordial00.'): raise AssertionError('legacy dependency: '+fullname)
sys.meta_path.insert(0,NoLegacy())
from digital_life.application.runtime.engine import Engine
from digital_life.entrypoints.cli import main
from digital_life.entrypoints.runtime import main as runtime
from digital_life.infrastructure.llm.inference import configured_reasoner
print('independent')
'''
        result=subprocess.run([sys.executable,'-c',code],cwd=PROJECT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn('independent',result.stdout)
    def test_compatibility_exports_reference_same_implementations(self):
        from digital_life.services import Memory as old_memory
        from digital_life.application.services.memory import Memory
        from digital_life.store import Store as old_store
        from digital_life.infrastructure.persistence.sqlite_store import Store
        self.assertIs(old_memory,Memory); self.assertIs(old_store,Store)
