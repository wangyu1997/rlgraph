# Copyright 2018/2019 The RLgraph authors, All Rights Reserved.
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

from rlgraph.components.component import Component
from rlgraph.components.neural_networks.preprocessor_stack import PreprocessorStack
from rlgraph.components.policies.policy import Policy
from rlgraph.components.explorations.exploration import Exploration
from rlgraph.utils.decorators import rlgraph_api


class ActorComponent(Component):
    """
    A Component that incorporates an entire pipeline from env state to an action choice.
    Includes preprocessor, policy and exploration sub-components.
    """
    def __init__(self, preprocessor_spec, policy_spec, exploration_spec=None,
                 **kwargs):
        """
        Args:
            preprocessor_spec (Union[list,dict,PreprocessorSpec]):
                - A dict if the state from the Env will come in as a ContainerSpace (e.g. Dict). In this case, each
                    each key in this dict specifies, which value in the incoming dict should go through which PreprocessorStack.
                - A list with layer specs.
                - A PreprocessorStack object.
            policy_spec (Union[dict,Policy]): A specification dict for a Policy object or a Policy object directly.
            exploration_spec (Union[dict,Exploration]): A specification dict for an Exploration object or an Exploration
                object directly.
        """
        super(ActorComponent, self).__init__(scope=kwargs.pop("scope", "actor-component"), **kwargs)

        self.preprocessor = PreprocessorStack.from_spec(preprocessor_spec)
        self.policy = Policy.from_spec(policy_spec)
        self.exploration = Exploration.from_spec(exploration_spec)

        self.add_components(self.policy, self.exploration, self.preprocessor)

    @rlgraph_api
    def get_preprocessed_state_and_action(self, states, internal_states=None, time_step=0, use_exploration=True):
        """
        API-method to get the preprocessed state and an action based on a raw state from an Env.

        Args:
            states (DataOp): The states coming directly from the environment.
            internal_states (DataOp): The initial internal states to use (in case of an RNN network).
            time_step (DataOp): The current time step(s).
            use_exploration (Optional[DataOp]): Whether to use exploration or not.

        Returns:
            dict (3x DataOp):
                `preprocessed_state` (DataOp): The preprocessed states.
                `action` (DataOp): The chosen action.
                `last_internal_states` (DataOp): If RNN-based, the last internal states after passing through
                states. Or None.
        """
        preprocessed_states = self.preprocessor.preprocess(states)

        out = self.policy.get_action(preprocessed_states, internal_states=internal_states)

        actions = self.exploration.get_action(out["action"], time_step, use_exploration)
        return dict(
            preprocessed_state=preprocessed_states, action=actions, last_internal_states=out["last_internal_states"]
        )

    @rlgraph_api
    def get_preprocessed_state_action_and_action_probs(
            self, states, internal_states=None, time_step=0, use_exploration=True
    ):
        """
        API-method to get the preprocessed state, one action and all possible action's probabilities based on a
        raw state from an Env.

        Args:
            states (DataOp): The states coming directly from the environment.
            internal_states (DataOp): The initial internal states to use (in case of an RNN network).
            time_step (DataOp): The current time step(s).
            use_exploration (Optional[DataOp]): Whether to use exploration or not.

        Returns:
            dict (4x DataOp):
                `preprocessed_state` (DataOp): The preprocessed states.
                `action` (DataOp): The chosen action.
                `action_probs` (DataOp): The different action probabilities.
                `last_internal_states` (DataOp): If RNN-based, the last internal states after passing through
                states. Or None.
        """
        preprocessed_states = self.preprocessor.preprocess(states)

        # TODO: Dynamic Batching problem. State-value is not really needed, but dynamic batching will require us to
        # TODO: run through the exact same partial-graph as the learner (which does need the extra state-value output).
        # if isinstance(self.policy, SharedValueFunctionPolicy):
        #    out = self.policy.get_state_values_logits_probabilities_log_probs(preprocessed_states, internal_states)
        # else:
        out = self.policy.get_logits_parameters_log_probs(preprocessed_states, internal_states)

        action_sample = self.policy.get_action_from_logits_and_probabilities(out["logits"], out["parameters"])

        actions = self.exploration.get_action(action_sample["action"], time_step, use_exploration)
        return dict(
            preprocessed_state=preprocessed_states, action=actions, action_probs=out["parameters"],
            last_internal_states=out["last_internal_states"]
        )
