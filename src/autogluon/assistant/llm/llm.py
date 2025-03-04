import logging
import os
import pprint
from typing import Any, Dict, List, Union

import boto3
import botocore
from langchain.schema import AIMessage, BaseMessage
from langchain_aws import ChatBedrock
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from omegaconf import DictConfig
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from autogluon.assistant.constants import WHITE_LIST_LLM

logger = logging.getLogger(__name__)


class AssistantChatOpenAI(ChatOpenAI, BaseModel):
    """
    AssistantChatOpenAI is a subclass of ChatOpenAI that traces the input and output of the model.
    """

    history_: List[Dict[str, Any]] = Field(default_factory=list)
    input_: int = Field(default=0)
    output_: int = Field(default=0)

    def describe(self) -> Dict[str, Any]:
        return {
            "model": self.model_name,
            "proxy": self.openai_proxy,
            "history": self.history_,
            "prompt_tokens": self.input_,
            "completion_tokens": self.output_,
        }

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
    def invoke(self, *args, **kwargs):
        input_: List[BaseMessage] = args[0]
        response = super().invoke(*args, **kwargs)

        # Update token usage
        if isinstance(response, AIMessage) and response.usage_metadata:
            self.input_ += response.usage_metadata.get("input_tokens", 0)
            self.output_ += response.usage_metadata.get("output_tokens", 0)

        self.history_.append(
            {
                "input": [{"type": msg.type, "content": msg.content} for msg in input_],
                "output": pprint.pformat(dict(response)),
                "prompt_tokens": self.input_,
                "completion_tokens": self.output_,
            }
        )
        return response


class AssistantAzureChatOpenAI(AzureChatOpenAI, BaseModel):
    """
    AssistantAzureChatOpenAI is a subclass of AzureChatOpenAI that traces the input and output of the model.
    """

    history_: List[Dict[str, Any]] = Field(default_factory=list)
    input_: int = Field(default=0)
    output_: int = Field(default=0)

    def describe(self) -> Dict[str, Any]:
        return {
            "model": self.model_name,
            "proxy": self.openai_proxy,
            "history": self.history_,
            "prompt_tokens": self.input_,
            "completion_tokens": self.output_,
        }

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
    def invoke(self, *args, **kwargs):
        input_: List[BaseMessage] = args[0]
        response = super().invoke(*args, **kwargs)

        # Update token usage
        if isinstance(response, AIMessage) and response.usage_metadata:
            self.input_ += response.usage_metadata.get("input_tokens", 0)
            self.output_ += response.usage_metadata.get("output_tokens", 0)

        self.history_.append(
            {
                "input": [{"type": msg.type, "content": msg.content} for msg in input_],
                "output": pprint.pformat(dict(response)),
                "prompt_tokens": self.input_,
                "completion_tokens": self.output_,
            }
        )
        return response


class AssistantChatBedrock(ChatBedrock, BaseModel):
    """
    AssistantChatBedrock is a subclass of ChatBedrock that traces the input and output of the model.
    """

    history_: List[Dict[str, Any]] = Field(default_factory=list)
    input_: int = Field(default=0)
    output_: int = Field(default=0)

    def describe(self) -> Dict[str, Any]:
        return {
            "model": self.model_id,
            "history": self.history_,
            "prompt_tokens": self.input_,
            "completion_tokens": self.output_,
        }

    @retry(stop=stop_after_attempt(50), wait=wait_exponential(multiplier=1, min=4, max=10))
    def invoke(self, *args, **kwargs):
        input_: List[BaseMessage] = args[0]
        try:
            response = super().invoke(*args, **kwargs)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                raise e
            else:
                raise e

        # Update token usage
        if isinstance(response, AIMessage) and response.usage_metadata:
            self.input_ += response.usage_metadata.get("input_tokens", 0)
            self.output_ += response.usage_metadata.get("output_tokens", 0)

        self.history_.append(
            {
                "input": [{"type": msg.type, "content": msg.content} for msg in input_],
                "output": pprint.pformat(dict(response)),
                "prompt_tokens": self.input_,
                "completion_tokens": self.output_,
            }
        )
        return response


class AssistantChatDeepSeek(ChatOpenAI, BaseModel):
    """
    AssistantChatDeepSeek is a subclass of ChatOpenAI that traces the input and output of the model
    and provides integration with DeepSeek API.
    """

    history_: List[Dict[str, Any]] = Field(default_factory=list)
    input_: int = Field(default=0)
    output_: int = Field(default=0)

    def describe(self) -> Dict[str, Any]:
        return {
            "model": self.model_name,
            "proxy": self.openai_proxy,
            "history": self.history_,
            "prompt_tokens": self.input_,
            "completion_tokens": self.output_,
        }

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
    def invoke(self, *args, **kwargs):
        input_: List[BaseMessage] = args[0]
        response = super().invoke(*args, **kwargs)

        # Update token usage
        if isinstance(response, AIMessage) and response.usage_metadata:
            self.input_ += response.usage_metadata.get("input_tokens", 0)
            self.output_ += response.usage_metadata.get("output_tokens", 0)

        self.history_.append(
            {
                "input": [{"type": msg.type, "content": msg.content} for msg in input_],
                "output": pprint.pformat(dict(response)),
                "prompt_tokens": self.input_,
                "completion_tokens": self.output_,
            }
        )
        return response


class LLMFactory:
    @staticmethod
    def get_openai_models() -> List[str]:
        try:
            client = OpenAI()
            models = client.models.list()
            return [model.id for model in models if model.id.startswith(("gpt-3.5", "gpt-4"))]
        except Exception as e:
            print(f"Error fetching OpenAI models: {e}")
            return []

    @staticmethod
    def get_bedrock_models() -> List[str]:
        try:
            # TODO: Remove hardcoding AWS region
            bedrock = boto3.client("bedrock", region_name="us-west-2")
            response = bedrock.list_foundation_models()
            return [model["modelId"] for model in response["modelSummaries"]]
        except Exception as e:
            print(f"Error fetching Bedrock models: {e}")
            return []

    @staticmethod
    def get_azure_models() -> List[str]:
        try:
            client = AzureOpenAI()
            models = client.models.list()
            return [model.id for model in models if model.id.startswith(("gpt-3.5", "gpt-4"))]
        except Exception as e:
            print(f"Error fetching Azure models: {e}")
            return []

    @staticmethod
    def get_deepseek_models() -> List[str]:
        try:
            # DeepSeek не предоставляет API для получения списка моделей
            # Возвращаем фиксированный список доступных моделей
            return ["deepseek-chat", "deepseek-reasoner"]
        except Exception as e:
            print(f"Error with DeepSeek models: {e}")
            return []

    @classmethod
    def get_valid_models(cls, provider):
        if provider == "azure":
            return cls.get_azure_models()
        elif provider == "openai":
            return cls.get_openai_models()
        elif provider == "bedrock":
            model_names = cls.get_bedrock_models()
            assert len(model_names), "Check your bedrock keys"
            return model_names
        elif provider == "deepseek":
            return cls.get_deepseek_models()
        else:
            raise ValueError(f"Invalid LLM provider: {provider}")

    @classmethod
    def get_valid_providers(cls, only_available=False):
        """
        Get list of valid LLM providers.
        
        Args:
            only_available (bool): If True, return only providers that are available 
                                  (have required API keys set in environment)
        
        Returns:
            List[str]: List of valid provider names
        """
        providers = ["azure", "openai", "bedrock", "deepseek"]
        
        if only_available:
            available_providers = []
            if "AZURE_OPENAI_API_KEY" in os.environ and "OPENAI_API_VERSION" in os.environ and "AZURE_OPENAI_ENDPOINT" in os.environ:
                available_providers.append("azure")
            if "OPENAI_API_KEY" in os.environ:
                available_providers.append("openai")
            # Bedrock uses AWS credentials
            try:
                boto3.client("bedrock", region_name="us-west-2").list_foundation_models()
                available_providers.append("bedrock")
            except:
                pass
            if "DEEPSEEK_API_KEY" in os.environ:
                available_providers.append("deepseek")
            return available_providers
        
        return providers

    @staticmethod
    def _get_azure_chat_model(
        config: DictConfig,
    ) -> AssistantAzureChatOpenAI:
        if "AZURE_OPENAI_API_KEY" in os.environ:
            api_key = os.environ["AZURE_OPENAI_API_KEY"]
        else:
            raise Exception("Azure API env variable AZURE_API_KEY not set")

        if "OPENAI_API_VERSION" not in os.environ:
            raise Exception("Azure API env variable OPENAI_API_VERSION not set")
        if "AZURE_OPENAI_ENDPOINT" not in os.environ:
            raise Exception("Azure API env variable AZURE_OPENAI_ENDPOINT not set")

        logger.info(f"AGA is using model {config.model} from Azure to assist you with the task.")
        return AssistantAzureChatOpenAI(
            api_key=api_key,
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            verbose=config.verbose,
        )

    @staticmethod
    def _get_openai_chat_model(
        config: DictConfig,
    ) -> AssistantChatOpenAI:
        if "OPENAI_API_KEY" in os.environ:
            api_key = os.environ["OPENAI_API_KEY"]
        else:
            raise Exception("OpenAI API env variable OPENAI_API_KEY not set")

        logger.info(f"AGA is using model {config.model} from OpenAI to assist you with the task.")
        return AssistantChatOpenAI(
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            verbose=config.verbose,
            openai_api_key=api_key,
            openai_api_base=config.proxy_url,
        )

    @staticmethod
    def _get_bedrock_chat_model(config: DictConfig) -> AssistantChatBedrock:
        logger.info(f"AGA is using model {config.model} from Bedrock to assist you with the task.")

        return AssistantChatBedrock(
            model_id=config.model,
            model_kwargs={
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            },
            # TODO: Remove hardcoding AWS region
            region_name="us-west-2",
            verbose=config.verbose,
        )

    @staticmethod
    def _get_deepseek_chat_model(config: DictConfig) -> AssistantChatDeepSeek:
        if "DEEPSEEK_API_KEY" in os.environ:
            api_key = os.environ["DEEPSEEK_API_KEY"]
        else:
            raise Exception("DeepSeek API env variable DEEPSEEK_API_KEY not set")

        logger.info(f"AGA is using model {config.model} from DeepSeek to assist you with the task.")
        return AssistantChatDeepSeek(
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            verbose=config.verbose,
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com",
        )

    @classmethod
    def get_chat_model(
        cls, config: DictConfig
    ) -> Union[AssistantChatOpenAI, AssistantAzureChatOpenAI, AssistantChatBedrock, AssistantChatDeepSeek]:
        valid_providers = cls.get_valid_providers()
        assert config.provider in valid_providers, f"{config.provider} is not a valid provider in: {valid_providers}"

        valid_models = cls.get_valid_models(config.provider)
        assert (
            config.model in valid_models
        ), f"{config.model} is not a valid model in: {valid_models} for provider {config.provider}"

        if config.model not in WHITE_LIST_LLM:
            logger.warning(f"{config.model} is not on the white list. Our white list models include {WHITE_LIST_LLM}")

        if config.provider == "azure":
            return LLMFactory._get_azure_chat_model(config)
        elif config.provider == "openai":
            return LLMFactory._get_openai_chat_model(config)
        elif config.provider == "bedrock":
            return LLMFactory._get_bedrock_chat_model(config)
        elif config.provider == "deepseek":
            return LLMFactory._get_deepseek_chat_model(config)
        else:
            raise ValueError(f"Invalid LLM provider: {config.provider}")
