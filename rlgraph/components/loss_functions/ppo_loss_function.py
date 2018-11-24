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

from rlgraph import get_backend
from rlgraph.components.helpers import GeneralizedAdvantageEstimation
from rlgraph.components.loss_functions import LossFunction
from rlgraph.utils.decorators import rlgraph_api

if get_backend() == "tf":
    import tensorflow as tf
elif get_backend() == "pytorch":
    import torch


class PPOLossFunction(LossFunction):
    """
    Loss function for proximal policy optimization:

    https://arxiv.org/abs/1707.06347
    """
    def __init__(self, discount=0.99, gae_lambda=1.0, clip_ratio=0.2, standardize_advantages=False, weight_entropy=None,
                 scope="ppo-loss-function", **kwargs):
        """
        Args:
            discount (float): The discount factor (gamma) to use.
            gae_lambda (float): Optional GAE discount factor.
            clip_ratio (float): How much to clip the likelihood ratio between old and new policy when updating.
            standardize_advantages (bool): If true, normalize advantage values in update.
            **kwargs:
        """
        self.clip_ratio = clip_ratio
        self.standardize_advantages = standardize_advantages
        self.weight_entropy = weight_entropy if weight_entropy is not None else 0.00025

        super(PPOLossFunction, self).__init__(scope=scope, **kwargs)

        self.gae_function = GeneralizedAdvantageEstimation(gae_lambda=gae_lambda, discount=discount)
        self.add_components(self.gae_function)

    @rlgraph_api
    def loss(self, log_probs, baseline_values, actions, rewards, terminals, sequence_indices, logits):
        """
        API-method that calculates the total loss (average over per-batch-item loss) from the original input to
        per-item-loss.

        Args: see `self._graph_fn_loss_per_item`.

        Returns:
            Total loss, loss per item, total baseline loss, baseline loss per item.
        """
        loss_per_item, baseline_loss_per_item = self.loss_per_item(
            log_probs, baseline_values, actions, rewards, terminals, sequence_indices, logits
        )
        total_loss = self.loss_average(loss_per_item)
        total_baseline_loss = self.loss_average(baseline_loss_per_item)

        return total_loss, loss_per_item, total_baseline_loss, baseline_loss_per_item

    @rlgraph_api
    def _graph_fn_loss_per_item(self, log_probs, baseline_values, actions, rewards, terminals, sequence_indices, logits):
        """
        Args:
            log_probs (SingleDataOp): Log-likelihoods of actions under policy.
            actions (SingleDataOp): The batch of actions that were actually taken in states s (from a memory).
            rewards (SingleDataOp): The batch of rewards that we received after having taken a in s (from a memory).
            terminals (SingleDataOp): The batch of terminal signals that we received after having taken a in s
                (from a memory).
            sequence_indices (DataOp): Int indices denoting sequences (which may be non-terminal episode fragments
                from multiple environments.
            logits (SingleDataOp): State logits.
        Returns:
            SingleDataOp: The loss values vector (one single value for each batch item).
        """
        if get_backend() == "tf":
            # N.b.: Many implementations do the following:
            # Sample action -> return policy log probs with action -> feed both back in from memory/via placeholders.
            # This creates the same effect as just stopping the gradients on the log-probs.
            prev_log_probs = tf.stop_gradient(log_probs)
            baseline_values = tf.squeeze(input=baseline_values, axis=-1)

            # Compute advantages.
            pg_advantages = self.gae_function.calc_gae_values(baseline_values, rewards, terminals, sequence_indices)

            if self.standardize_advantages:
                mean, std = tf.nn.moments(x=pg_advantages, axes=[0])
                pg_advantages = (pg_advantages - mean) / std

            v_targets = pg_advantages + baseline_values
            v_targets = tf.stop_gradient(input=v_targets)

            # Likelihood ratio and clipped objective.
            ratio = tf.exp(x=log_probs - prev_log_probs)
            clipped_advantages = tf.where(
                condition=pg_advantages > 0,
                x=(1 + self.clip_ratio) * pg_advantages,
                y=(1 - self.clip_ratio) * pg_advantages
            )

            loss = -tf.minimum(x=ratio * pg_advantages, y=clipped_advantages)
            # The entropy regularizer term.
            policy = tf.nn.softmax(logits=logits)
            log_policy = tf.nn.log_softmax(logits=logits)
            loss_entropy = tf.reduce_sum(-policy * log_policy, axis=-1)
            loss += self.weight_entropy * loss_entropy

            baseline_loss = (v_targets - baseline_values) ** 2

            return loss, baseline_loss
        elif get_backend() == "pytorch":
            # Detach grads.
            prev_log_probs = log_probs.detach()
            baseline_values = torch.squeeze(baseline_values, axis=-1)

            # Compute advantages.
            pg_advantages = self.gae_function.calc_gae_values(baseline_values, rewards, terminals, sequence_indices)

            if self.standardize_advantages:
                pg_advantages = (pg_advantages - torch.mean(pg_advantages)) / torch.std(pg_advantages)

            v_targets = pg_advantages + baseline_values
            v_targets = v_targets.detach()

            # Likelihood ratio and clipped objective.
            ratio = torch.exp(x=log_probs - prev_log_probs)
            clipped_advantages = torch.where(
                condition=pg_advantages > 0,
                x=(1 + self.clip_ratio) * pg_advantages,
                y=(1 - self.clip_ratio) * pg_advantages
            )

            loss = -torch.min(x=ratio * pg_advantages, y=clipped_advantages)
            # The entropy regularizer term.
            policy = torch.softmax(logits)
            log_policy = torch.log_softmax(logits)
            loss_entropy = torch.sum(-policy * log_policy, axis=-1)
            loss += self.weight_entropy * loss_entropy

            baseline_loss = (v_targets - baseline_values) ** 2
            return loss, baseline_loss
