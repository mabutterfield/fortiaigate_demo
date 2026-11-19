"""Compile catalog tool contracts into the MCP server's function format.

The generated registry is not installed automatically. Callers must explicitly
choose how to handle tools outside the active catalog before switching a server.
"""
from copy import deepcopy


def compile_registry(catalog):
    return [
        {'type': 'function', 'function': {'name': name, 'description': tool['description'],
                                          'parameters': deepcopy(tool['input_schema'])}}
        for name, tool in sorted(catalog['tools'].items())
    ]
