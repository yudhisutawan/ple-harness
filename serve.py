# Copyright 2026 Yudhi Sutawan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Entrypoint: serves `harness.solve` over the PLE serve protocol on `$PORT`.

Thin wrapper only — all agent logic lives in `harness.py`. The evaluator
starts this server once per task and connects over WebSocket; `taskbridge`
implements the protocol (copied from the official competition kit,
Apache-2.0, Google LLC).
"""

import harness
import taskbridge

if __name__ == "__main__":
    taskbridge.run(harness.solve)
