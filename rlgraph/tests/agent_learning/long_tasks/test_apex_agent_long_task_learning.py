# Copyright 2018 The RLgraph authors. All Rights Reserved.
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
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import os
import ray
import unittest

from rlgraph.agents import ApexAgent
from rlgraph.environments import OpenAIGymEnv
from rlgraph.execution.ray import ApexExecutor, RayWorker


class TestApexAgentLongTaskLearning(unittest.TestCase):
    """
    Tests whether the Apex Agent can start learning in pong.

    WARNING: This test requires large amounts of memory due to large buffer size.
    """
    env_spec = dict(
        type="openai",
        gym_env="Pong-v0",
        # The frameskip in the agent config will trigger.
        frameskip=4
    )

    def test_agent_compilation(self):
        """
        Tests agent compilation without Ray to ease debugging on Windows.
        """
        path = os.path.join(os.getcwd(), "../configs/ray_apex_for_pong.json")
        with open(path, 'rt') as fp:
            agent_config = json.load(fp)
            # Remove.
            agent_config["execution_spec"].pop("ray_spec")
        environment = OpenAIGymEnv("Pong-v0", frameskip=4 )

        agent = ApexAgent.from_spec(
            agent_config, state_space=environment.state_space, action_space=environment.action_space
        )
        print('Compiled apex agent')

    def test_worker_init(self):
        """
        Tests if workers initialize without problems for the pong config.
        """
        path = os.path.join(os.getcwd(), "../configs/ray_apex_for_pong.json")
        with open(path, 'rt') as fp:
            agent_config = json.load(fp)

        executor = ApexExecutor(
            environment_spec=self.env_spec,
            agent_config=agent_config,
        )
        executor.test_worker_init()

    def test_worker_update(self):
        """
        Tests if a worker can update from an external batch correct including all
        corrections and postprocessing using the pong spec.

        N.b. this test does not use Ray.
        """
        ray.init()
        path = os.path.join(os.getcwd(), "../configs/ray_apex_for_pong.json")
        with open(path, 'rt') as fp:
            agent_config = json.load(fp)

        worker_spec = agent_config["execution_spec"].pop("ray_spec")
        worker = RayWorker.remote(agent_config, self.env_spec, worker_spec)
        task = worker.execute_and_get_timesteps.remote(100, break_on_terminal=True)
        result = ray.get(task)
        print(result.get_metrics())

    def test_initial_training_pong(self):
        """
        Tests if Apex can start learning pong effectively on ray.
        """
        path = os.path.join(os.getcwd(), "../configs/ray_apex_for_pong.json")
        with open(path, 'rt') as fp:
            agent_config = json.load(fp)

        executor = ApexExecutor(
            environment_spec=self.env_spec,
            agent_config=agent_config,
        )

        # Executes actual workload.
        result = executor.execute_workload(workload=dict(num_timesteps=5000000, report_interval=5000))
        print("Finished executing workload:")
        print(result)
