# Copyright The Caikit Authors
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
"""
Huggingface auto causal LM resource type
"""
# Standard
from typing import Callable, List, Tuple, Union

# Third Party
from torch.utils.data import IterableDataset
from transformers import (
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)
from transformers.models.auto import modeling_auto

# First Party
from caikit.core.modules import module
from caikit.core.toolkit import error_handler
import alog

# Local
from ...data_model import GenerationTrainRecord, PromptOutputModelType
from ...toolkit.verbalizer_utils import render_verbalizer
from .base import PretrainedModelBase

log = alog.use_channel("HFRBAS")
error = error_handler.get(log)

IGNORE_ID = -100


@module(
    id="6759e891-287b-405b-bd8b-54a4a4d51c25",
    name="HF Transformers Auto Seq2Seq LM",
    version="0.1.0",
)
class HFAutoSeq2SeqLM(PretrainedModelBase):
    """This resource (module) wraps a handle to a Huggingface
    AutoModelForSeq2SeqLM
    """

    MODEL_TYPE = AutoModelForSeq2SeqLM
    SUPPORTED_MODEL_TYPES = modeling_auto.MODEL_FOR_SEQ_TO_SEQ_CAUSAL_LM_MAPPING_NAMES
    TASK_TYPE = "SEQ_2_SEQ_LM"
    PROMPT_OUTPUT_TYPES = [PromptOutputModelType.ENCODER]
    MAX_NUM_TRANSFORMERS = 2

    @classmethod
    def get_num_transformers_submodules(
        cls, output_model_types: List[PromptOutputModelType]
    ):
        """Return number of applicable transformer submodules"""
        num_transformer_submodules = 0
        if PromptOutputModelType.ENCODER in output_model_types:
            num_transformer_submodules += 1
        if PromptOutputModelType.DECODER in output_model_types:
            num_transformer_submodules += 1
        error.value_check(
            "<NLP71505742E>", 0 < num_transformer_submodules <= cls.MAX_NUM_TRANSFORMERS
        )
        return num_transformer_submodules

    def get_trainer(
        self,
        train_dataset: IterableDataset,
        eval_dataset: Union[IterableDataset, None] = None,
        optimizers=(None, None),
        **kwargs
    ):
        """
        NOTE: following parameters are not supported currently:
            1. model_init
            2. compute_metrics
            3. callbacks
            4. preprocess_logits_for_metrics
        """

        training_args = Seq2SeqTrainingArguments(predict_with_generate=True, **kwargs)

        # pylint: disable=duplicate-code
        # TODO: Fetch DataCollator either from property of this
        # class or fetch it as an argument.
        data_collator = self._get_data_collator(**kwargs)

        trainer_arguments = {
            "train_dataset": train_dataset,
            "data_collator": data_collator,
            "tokenizer": self._tokenizer,
            "optimizers": optimizers,
            "eval_dataset": eval_dataset,
            # "generation_max_length": max_target_length,
        }

        return Seq2SeqTrainer(self._model, training_args, **trainer_arguments)

    def _get_data_collator(self, **kwargs):
        """Function to return appropriate data collator based on resource.

        This implementation uses DataCollatorForSeq2Seq

        Args:
            **kwargs:
                All the keyword arguments passed to this function
                will get filtered out to appropriate ones that are
                applicable to implemented data collator.
        Returns:
            transformers.DataCollator
        """

        applicable_args = ["max_length", "pad_to_multiple_of"]
        collator_kwargs = {key: kwargs[key] for key in applicable_args if key in kwargs}

        return DataCollatorForSeq2Seq(
            tokenizer=self._tokenizer, model=self._model, **collator_kwargs
        )

    @staticmethod
    def build_task_tokenize_function(
        tokenizer: "AutoTokenizer",
        max_source_length: int,
        max_target_length: int,
        verbalizer: str,
        task_ids: Union[None, int] = None,
    ) -> Tuple[Callable, bool]:
        """Builds tokenizer functions which can be mapped over train streams to process
        data which can then be easily passed to a DataLoader for seq2seq models.

        Args:
            tokenizer: AutoTokenizer
                Model tokenizer to be used in preprocessing, i.e., when we iterate over our data.
            max_source_length: int
                Max length of sequences being considered.
            max_target_length: int
                Max length of target sequences being predicted.
            verbalizer: str
                Verbalizer template to be used for formatting data. This template may use brackets
                to indicate where fields from the data model TrainGenerationRecord must be rendered.
            task_ids: Union[None, int]
                Task id corresponding particular task for multi-task prompt tuning.
                NOTE: Only required for MPT (Multi-task prompt tuning)
                Default: None

        Returns:
            Tuple(Callable, bool)
                Mappable tokenize function to be applied to a training stream and bool indicating
                whether or not the stream needs to be unwrapped, i.e., each sample yields a stream
                of 1+ samples.
        """

        def tokenize_function_seq2seq(
            example: GenerationTrainRecord,
        ) -> "BatchEncoding":
            """Tokenization function to be used for seq2seq training; this function consumes a
            GenerationTrainRecord object and applies the verbalizer to it followed by
            the model tokenizer. Finally, we postprocess by ignoring pad tokens in the label IDs.

            Args:
                example: GenerationTrainRecord
                    Training data model object to convert a form we can learn on.

            Returns:
                transformers.tokenization_utils_base.BatchEncoding
                    encoded tokenization output corresponding to the input example.
            """
            # Render the verbalizer template with the attributes of this data model example
            source = render_verbalizer(verbalizer, example)

            targets = example.output
            model_inputs = tokenizer(
                source,
                max_length=max_source_length,
                padding="max_length",
                truncation=True,
            )
            labels = tokenizer(
                targets,
                max_length=max_target_length,
                padding="max_length",
                truncation=True,
            )

            labels = labels["input_ids"]

            labels = list(
                map(lambda x: IGNORE_ID if x == tokenizer.pad_token_id else x, labels)
            )
            model_inputs["labels"] = labels
            if task_ids is not None:
                model_inputs["task_ids"] = task_ids

            return model_inputs

        return (tokenize_function_seq2seq, False)
