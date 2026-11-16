"""Compatibility build for the system Python's pre-PEP-621 setuptools."""
from setuptools import setup,find_packages
import ast
from pathlib import Path

version_tree=ast.parse((Path(__file__).parent/'digital_life/__init__.py').read_text())
version=next(ast.literal_eval(node.value) for node in version_tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='__version__' for target in node.targets))

setup(name='ai-assistant-with-memory',version=version,
    description='Modular persistent digital life runtime and isolated acceptance tools',
    python_requires='>=3.9',install_requires=[],
    license='MIT',license_files=['LICENSE'],
    long_description=(Path(__file__).parent/'README.md').read_text(encoding='utf-8'),
    long_description_content_type='text/markdown',
    packages=find_packages(include=['digital_life','digital_life.*','primordial00','primordial00.*']),
    package_data={'digital_life':['resources/*.sql','resources/*.json','web/*.html','web/*.css','web/*.js'],
                  'primordial00':['resources/*.sql']},
    entry_points={'console_scripts':['digital-life=digital_life.__main__:main','primordial00=primordial00.__main__:main']})
