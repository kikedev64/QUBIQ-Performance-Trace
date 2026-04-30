[![Build Status](https://github.com/<your-user>/qubiq-performance-trace/actions/workflows/test.yml/badge.svg)](https://github.com/<your-user>/qubiq-performance-trace/actions)
[![codecov](https://codecov.io/gh/<your-user>/qubiq-performance-trace/branch/main/graph/badge.svg)](https://codecov.io/gh/<your-user>/qubiq-performance-trace)
[![License: OPL-1](https://img.shields.io/badge/license-OPL--1-blue.svg)](LICENSE)

<!-- /!\ do not modify above this line -->

# QUBIQ Performance Trace

Real-time Python performance tracing tool for Odoo.

This module provides a lightweight and visual way to inspect execution flow,
nested function calls, and performance bottlenecks directly from a web browser.

It is especially useful for debugging complex business logic, ORM calls, and
hidden performance issues inside Odoo.

---

## Overview

`qubiq_performance_trace` uses Python's low-level profiling system (`sys.setprofile`)
to capture function calls during the execution of decorated methods.

Captured events are:

- Measured (execution time)
- Structured (call hierarchy)
- Filtered (include/exclude modules)
- Streamed in real time to a browser UI

---

## Features

- Real-time execution tracing (Server-Sent Events)
- Hierarchical call tree visualization
- Color-based performance classification
- Include and exclude module filters
- Minimum execution time filtering
- Persistent in-memory history (survives reload)
- Zero external dependencies
- Fully integrated with Odoo

---

## Usage

### Decorate any method

```python
from odoo.addons.qubiq_performance_trace.tools import trace_performance

@trace_performance(
    module_filter="/custom/src/",
    exclude_filter="/odoo/odoo/",
    min_time=0.05,
)
def action_approve(self):
````

## Installation

Copy the module into the private addons directory:

```bash
cp -r qubiq_performance_trace /path/to/odoo/custom/src/private/
````

Then add the trace proxy service inside the `services` section of your `docker-compose.yaml`:

```yaml
trace_proxy:
    image: tecnativa/whitelist
    depends_on:
        - odoo
    networks:
        default:
        public:
    ports:
        - "127.0.0.1:8079:8079"
    environment:
        PORT: 8079
        TARGET: odoo
```

After that, restart the environment and install the module from Odoo Apps, or update it. 
Once installed, import and add the decorator to the method you want to trace:

```python
from odoo.addons.qubiq_performance_trace.tools import trace_performance


@trace_performance(
    module_filter=None,
    exclude_filter=[
        "/opt/odoo/custom/src/odoo/odoo/",
    ],
    min_time=0.05,
)
def action_approve(self):
    ...
```

Open the trace interface at:

```text
http://127.0.0.1:8079
```

## Copyright

Copyright 2026 QUBIQ.

Website: [https://www.qubiq.es](https://www.qubiq.es)

This module is distributed under the OPL-1.0 license.
