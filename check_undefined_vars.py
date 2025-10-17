#!/usr/bin/env python3
"""
AST-based checker for undefined variables in Python code.
This script analyzes Python files to find potential undefined variables.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Set, List, Tuple, Dict
import builtins

class UndefinedVariableFinder(ast.NodeVisitor):
    """Find undefined variables using AST analysis."""

    def __init__(self):
        self.defined_names: Set[str] = set()
        self.used_names: Set[str] = set()
        self.scopes: List[Set[str]] = []
        self.imports: Set[str] = set()
        self.undefined: List[Tuple[str, int, int]] = []
        self.current_class: str = None
        self.builtin_names = set(dir(builtins))

        # Common Python globals
        self.global_names = {
            '__name__', '__file__', '__doc__', '__package__',
            '__loader__', '__spec__', '__annotations__', '__builtins__',
            '__cached__', '__dict__', 'self', 'cls'
        }

    def visit_FunctionDef(self, node):
        self.defined_names.add(node.name)
        # Enter new scope
        new_scope = set()
        # Add function parameters to scope
        for arg in node.args.args:
            new_scope.add(arg.arg)
        if node.args.vararg:
            new_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            new_scope.add(node.args.kwarg.arg)
        for arg in node.args.kwonlyargs:
            new_scope.add(arg.arg)

        self.scopes.append(new_scope)
        self.generic_visit(node)
        self.scopes.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.defined_names.add(node.name)
        old_class = self.current_class
        self.current_class = node.name
        self.scopes.append(set())
        self.generic_visit(node)
        self.scopes.pop()
        self.current_class = old_class

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name.split('.')[0]
            self.imports.add(name)
            self.defined_names.add(name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports.add(name)
            self.defined_names.add(name)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            # Variable is being defined
            if self.scopes:
                self.scopes[-1].add(node.id)
            else:
                self.defined_names.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            # Variable is being used
            name = node.id

            # Check if it's defined in any scope
            in_scope = False
            for scope in self.scopes:
                if name in scope:
                    in_scope = True
                    break

            if not in_scope and name not in self.defined_names \
               and name not in self.imports \
               and name not in self.builtin_names \
               and name not in self.global_names:
                # Special handling for class attributes
                if self.current_class and name == self.current_class:
                    pass  # Class can reference itself
                else:
                    self.undefined.append((name, node.lineno, node.col_offset))

    def visit_For(self, node):
        # Add loop variable to current scope
        if isinstance(node.target, ast.Name):
            if self.scopes:
                self.scopes[-1].add(node.target.id)
            else:
                self.defined_names.add(node.target.id)
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                if self.scopes:
                    self.scopes[-1].add(item.optional_vars.id)
                else:
                    self.defined_names.add(item.optional_vars.id)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node):
        if node.name:
            if self.scopes:
                self.scopes[-1].add(node.name)
            else:
                self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_ListComp(self, node):
        # List comprehensions have their own scope
        new_scope = set()
        for generator in node.generators:
            if isinstance(generator.target, ast.Name):
                new_scope.add(generator.target.id)
        self.scopes.append(new_scope)
        self.generic_visit(node)
        self.scopes.pop()

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp


def check_file(filepath: Path) -> List[Dict]:
    """Check a single Python file for undefined variables."""
    issues = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content, filename=str(filepath))
        finder = UndefinedVariableFinder()
        finder.visit(tree)

        for name, line, col in finder.undefined:
            issues.append({
                'file': str(filepath),
                'line': line,
                'col': col,
                'variable': name,
                'context': get_line_context(filepath, line)
            })

    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}")
    except Exception as e:
        print(f"Error processing {filepath}: {e}")

    return issues


def get_line_context(filepath: Path, line_num: int) -> str:
    """Get the line of code at the specified line number."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if 0 < line_num <= len(lines):
                return lines[line_num - 1].strip()
    except:
        pass
    return ""


def main():
    # Directories to check
    dirs_to_check = [
        'core',
        'database',
        'monitoring',
        'protection',
        'utils',
        'websocket'
    ]

    # Files to check in root
    root_files = [
        'main.py',
        'config.py'
    ]

    all_issues = []
    files_checked = 0

    print("=== AST-BASED UNDEFINED VARIABLE CHECKER ===\n")

    # Check directories
    for dir_name in dirs_to_check:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"Checking {dir_name}/...")
            for py_file in dir_path.glob("**/*.py"):
                # Skip test files and __pycache__
                if 'test' in str(py_file).lower() or '__pycache__' in str(py_file):
                    continue

                issues = check_file(py_file)
                if issues:
                    all_issues.extend(issues)
                files_checked += 1

    # Check root files
    for filename in root_files:
        filepath = Path(filename)
        if filepath.exists():
            print(f"Checking {filename}...")
            issues = check_file(filepath)
            if issues:
                all_issues.extend(issues)
            files_checked += 1

    # Report results
    print(f"\n=== RESULTS ===")
    print(f"Files checked: {files_checked}")
    print(f"Issues found: {len(all_issues)}\n")

    if all_issues:
        print("UNDEFINED VARIABLES FOUND:\n")
        for issue in all_issues:
            print(f"❌ {issue['file']}:{issue['line']}:{issue['col']}")
            print(f"   Variable: '{issue['variable']}'")
            print(f"   Context: {issue['context']}")
            print()
    else:
        print("✅ No undefined variables found!")

    return len(all_issues)


if __name__ == "__main__":
    sys.exit(main())