#!/usr/bin/env python3
"""
Build script to create a monolithic version from modular components.

This script combines all module files into a single replace_control_plane.py file
while removing import statements and maintaining proper execution order.
"""
import os
import re
from datetime import datetime


def read_module_file(module_path):
    """Read a module file and strip module-specific imports and docstrings."""
    with open(module_path, "r") as f:
        content = f.read()

    # Remove shebang, module docstring, and imports (except type-only imports)
    lines = content.split("\n")
    filtered_lines = []
    in_module_docstring = False

    for line in lines:
        # Skip shebang
        if line.startswith("#!/usr/bin/env python3"):
            continue

        # Skip module-level docstring
        if line.strip().startswith('"""') and not in_module_docstring:
            if line.count('"""') >= 2:  # Single line docstring
                continue
            in_module_docstring = True
            continue
        elif line.strip().endswith('"""') and in_module_docstring:
            in_module_docstring = False
            continue
        elif in_module_docstring:
            continue

        # Skip import statements but preserve type-only imports as comments for reference
        stripped_line = line.strip()
        if (
            stripped_line.startswith("from ")
            or stripped_line.startswith("import ")
            or stripped_line.startswith("from.")
            or stripped_line.startswith("import.")
        ):
            # Convert type-only imports to comments for debugging
            if "typing" in stripped_line or "PrintManager" in stripped_line:
                filtered_lines.append(f"# {line}")
            continue

        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def build_monolith():
    """Build monolithic version from modules."""
    # Script is now in replace_control_plane/scripts/, so go up one level to get to source_dir
    source_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    modules_dir = os.path.join(source_dir, "modules")
    modular_file = os.path.join(source_dir, "replace_control_plane_modular.py")
    output_file = os.path.join(source_dir, "replace_control_plane.py")

    print(f"Building monolith from: {modules_dir}")
    print(f"Main script: {modular_file}")
    print(f"Output: {output_file}")

    # Start with base imports and header
    monolith_content = f"""#!/usr/bin/env python3
'''
OpenShift Control Plane Replacement Tool - Monolithic Version

This monolithic version contains all components in a single file for easy distribution.
Generated automatically from modular components on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.

For development, use the modular version in modules/ directory.
'''

import argparse
import base64
import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Dict, Optional, Tuple

import yaml

"""

    # Module loading order (dependencies first)
    module_order = [
        "print_manager.py",
        "utilities.py",
        "backup_manager.py",
        "node_configurator.py",
        "arguments_parser.py",
        "resource_monitor.py",
        "etcd_manager.py",
        "configuration_manager.py",
        "resource_manager.py",
        "orchestrator.py",
    ]

    # Add each module's content
    for module_name in module_order:
        module_path = os.path.join(modules_dir, module_name)
        if os.path.exists(module_path):
            print(f"Adding module: {module_name}")
            module_content = read_module_file(module_path)
            # Clean up excessive blank lines and normalize spacing
            module_content = re.sub(r"\n\n\n+", "\n\n", module_content)
            monolith_content += f"\n\n# === {module_name.replace('.py', '').upper()} MODULE ===\n\n"
            monolith_content += module_content
        else:
            print(f"Warning: Module not found: {module_path}")

        # Add global instances for monolithic version
    monolith_content += """

# === GLOBAL INSTANCES ===

# Global printer instance
printer = PrintManager()
print_manager = printer  # Alias for backward compatibility

"""

    # Read the main function from modular version
    with open(modular_file, "r") as f:
        main_content = f.read()

    # Extract main function and entry point
    main_match = re.search(r"def main\(\):.*?(?=\n\ndef|\nif __name__|$)", main_content, re.DOTALL)
    if main_match:
        main_function = main_match.group(0)

        # Remove module imports from main function
        main_function = re.sub(r"from modules import.*?\n", "", main_function)
        main_function = re.sub(r"import.*?modules.*?\n", "", main_function, flags=re.MULTILINE)

        monolith_content += f"\n# === MAIN FUNCTION ===\n{main_function}\n\n"
        monolith_content += 'if __name__ == "__main__":\n    main()\n'
    else:
        print("Warning: Could not extract main function")

    # Final cleanup: normalize all blank lines throughout the monolithic content
    monolith_content = re.sub(r"\n\n\n\n+", "\n\n\n", monolith_content)  # Max 3 newlines
    monolith_content = re.sub(r"\n\n\n+$", "\n", monolith_content)  # Clean up end of file

    # Write the monolithic file
    with open(output_file, "w") as f:
        f.write(monolith_content)

    print(f"Monolithic version created: {output_file}")
    return output_file


if __name__ == "__main__":
    build_monolith()
