from fastmcp import FastMCP
from typing import Dict, Any, Optional, List, Annotated, Union
import structlog
from datetime import datetime, timedelta
import json
import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from openai import AsyncOpenAI
from pydantic import Field, BaseModel, ValidationError
from utils.http_client import api_client

logger = structlog.get_logger()

class ProcessingStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    CLARIFICATION_NEEDED = "clarification_needed"

@dataclass
class ExtractedWhistleData:
    """Data class for extracted whistle information"""
    description: str
    alert_radius: int = 2
    tags: List[str] = None
    provider: Optional[bool] = None
    expiry: str = "never"
    ask_again: bool = False
    reason: str = ""
    confidence_score: float = 0.0
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class AdvancedLLMExtractor:
    """Pure LLM-based extraction using OpenAI"""
    
    def __init__(self):
        self.openai_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.default_radius = 2
        self.default_expiry_days = 7
    
    async def extract_attributes(self, user_input: str) -> ExtractedWhistleData:
        """Extract whistle attributes using OpenAI GPT"""
        try:
            if not os.getenv("OPENAI_API_KEY"):
                return ExtractedWhistleData(
                    description=user_input,
                    ask_again=True,
                    reason="OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.",
                    confidence_score=0.0
                )
            
            return await self._extract_with_openai(user_input)
            
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {str(e)}")
            return ExtractedWhistleData(
                description=user_input,
                ask_again=True,
                reason=f"Unable to process request: {str(e)}",
                confidence_score=0.0
            )
    
    async def _extract_with_openai(self, user_input: str) -> ExtractedWhistleData:
        """Advanced OpenAI extraction with multi-step reasoning"""
        
        # Step 1: Primary extraction
        primary_result = await self._primary_extraction(user_input)
        
        # Step 2: Validation and confidence scoring
        validation_result = await self._validate_and_score(user_input, primary_result)
        
        # Step 3: Enhancement if confidence is low
        if validation_result.get("confidence", 0) < 0.7:
            enhanced_result = await self._enhance_extraction(user_input, primary_result)
            return self._create_extraction_result(user_input, enhanced_result)
        
        return self._create_extraction_result(user_input, validation_result)
    
    async def _primary_extraction(self, user_input: str) -> Dict[str, Any]:
        """Primary extraction using comprehensive LLM reasoning"""
        
        system_prompt = """You are an expert at understanding service requests and offers. Your job is to analyze text and extract structured information about services.

You must analyze the input and extract these attributes with reasoning:

1. SERVICE TAGS: What specific services, skills, or help are mentioned? Think broadly - any profession, skill, task, or assistance type
2. PROVIDER STATUS: Is the person offering services (provider=true) or seeking services (provider=false)?
3. LOCATION SCOPE: Any distance or area mentioned? Convert to kilometers if needed
4. TIME FRAME: Any time references? Convert to future datetime
5. CLARITY: Is the request clear enough to act on?

Be creative and comprehensive in identifying services. Consider:
- Professional services (plumber, teacher, developer, etc.)
- Skills (coding, cooking, tutoring, etc.) 
- Tasks (cleaning, delivery, repair, etc.)
- General help categories (moving, babysitting, etc.)
- Creative services (writing, design, photography, etc.)

Always think step-by-step and explain your reasoning."""

        user_prompt = f"""Analyze this text and extract service information: "{user_input}"

Current date and time: {datetime.now().isoformat()}

Think through this step by step:
1. What services/skills/help are being discussed?
2. Is this person offering to provide something or asking for something?
3. Any location/distance mentioned?
4. Any time constraints mentioned?
5. Is this clear enough to create a service request?

Respond with valid JSON in this exact format:
{{
    "reasoning": "your step-by-step analysis",
    "services_identified": ["list", "of", "services", "found"],
    "provider": true/false/null,
    "provider_reasoning": "why you determined this",
    "alert_radius_km": number,
    "distance_reasoning": "how you determined radius",
    "expiry_iso": "ISO datetime string or 'default'",
    "time_reasoning": "how you determined timing",
    "clarity_score": 0.0-1.0,
    "clarity_reasoning": "why this score",
    "needs_clarification": true/false,
    "clarification_reason": "what needs clarification"
}}"""

        return await self._call_openai(system_prompt, user_prompt)
    
    async def _validate_and_score(self, user_input: str, primary_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate extraction and provide confidence scoring"""
        
        system_prompt = """You are a validator for service request extractions. Your job is to check if the extracted information makes sense and is actionable.

Evaluate the extraction quality and provide confidence scoring."""

        user_prompt = f"""Original input: "{user_input}"

Extracted data: {json.dumps(primary_result, indent=2)}

Validate this extraction:
1. Do the identified services make sense for the input?
2. Is the provider determination logical?
3. Are the time/location inferences reasonable?
4. Is this actionable as a service request/offer?

Respond with valid JSON:
{{
    "validation_passed": true/false,
    "confidence": 0.0-1.0,
    "issues_found": ["list", "of", "any", "issues"],
    "suggested_improvements": ["list", "of", "suggestions"],
    "final_services": ["refined", "service", "list"],
    "final_provider": true/false/null,
    "final_radius": number,
    "final_expiry": "ISO datetime or 'default'",
    "actionable": true/false
}}"""

        return await self._call_openai(system_prompt, user_prompt)
    
    async def _enhance_extraction(self, user_input: str, primary_result: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance extraction for low-confidence cases"""
        
        system_prompt = """You are an enhancement specialist for unclear service requests. Your job is to make the best possible interpretation of ambiguous inputs.

Use contextual reasoning to fill gaps and make reasonable assumptions."""

        user_prompt = f"""Original input: "{user_input}"
Primary extraction: {json.dumps(primary_result, indent=2)}

This extraction had low confidence. Please enhance it by:
1. Making reasonable assumptions about unclear services
2. Using context clues to determine provider/seeker status
3. Inferring appropriate defaults for missing information
4. Deciding if it's actionable with reasonable assumptions

Respond with valid JSON:
{{
    "enhanced_services": ["best", "guess", "services"],
    "enhanced_provider": true/false/null,
    "enhanced_radius": number,
    "enhanced_expiry": "ISO datetime or 'default'",
    "assumptions_made": ["list", "of", "assumptions"],
    "confidence": 0.0-1.0,
    "actionable_with_assumptions": true/false,
    "clarification_needed": true/false,
    "clarification_question": "specific question to ask user"
}}"""

        return await self._call_openai(system_prompt, user_prompt)
    
    async def _call_openai(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Make OpenAI API call with error handling"""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                timeout=30.0
            )
            
            content = response.choices[0].message.content
            
            # Clean and parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI JSON response: {content}")
            raise Exception(f"Invalid JSON response from OpenAI: {str(e)}")
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _create_extraction_result(self, user_input: str, llm_result: Dict[str, Any]) -> ExtractedWhistleData:
        """Create final extraction result from LLM output"""
        
        # Extract services (try different possible keys)
        services = (
            llm_result.get("final_services") or 
            llm_result.get("enhanced_services") or 
            llm_result.get("services_identified") or 
            []
        )
        
        # Extract provider status
        provider = (
            llm_result.get("final_provider") if "final_provider" in llm_result else
            llm_result.get("enhanced_provider") if "enhanced_provider" in llm_result else
            llm_result.get("provider")
        )
        
        # Extract radius
        radius = (
            llm_result.get("final_radius") or 
            llm_result.get("enhanced_radius") or 
            llm_result.get("alert_radius_km") or 
            self.default_radius
        )
        
        # Extract expiry
        expiry = (
            llm_result.get("final_expiry") or 
            llm_result.get("enhanced_expiry") or 
            llm_result.get("expiry_iso") or 
            "default"
        )
        
        if expiry == "default":
            expiry_date = datetime.now() + timedelta(days=self.default_expiry_days)
            expiry = expiry_date.isoformat() + "Z"
        
        # Determine if clarification needed
        needs_clarification = (
            llm_result.get("clarification_needed") or 
            llm_result.get("needs_clarification") or 
            not llm_result.get("actionable", True) or
            not llm_result.get("actionable_with_assumptions", True)
        )
        
        clarification_reason = (
            llm_result.get("clarification_question") or 
            llm_result.get("clarification_reason") or 
            "Could not clearly understand the service request"
        )
        
        confidence = (
            llm_result.get("confidence") or 
            llm_result.get("clarity_score") or 
            0.5
        )
        
        return ExtractedWhistleData(
            description=user_input,
            alert_radius=int(radius),
            tags=services,
            provider=provider,
            expiry=expiry,
            ask_again=needs_clarification,
            reason=clarification_reason if needs_clarification else "",
            confidence_score=confidence
        )
    
    async def _extract_with_simple_analysis(self, user_input: str) -> ExtractedWhistleData:
        """Fallback when OpenAI is not available or fails"""
        
        # This is a minimal fallback - requires OpenAI for full functionality
        return ExtractedWhistleData(
            description=user_input,
            ask_again=True,
            reason="OpenAI processing failed. Please be very specific about: 1) What service you need/offer, 2) Whether you're providing or seeking, 3) When you need it",
            confidence_score=0.1
        )

class WhistleValidator:
    """Validates extracted whistle data"""
    
    @staticmethod
    def validate_whistle_data(data: ExtractedWhistleData) -> Dict[str, Any]:
        """Validate extracted whistle data"""
        errors = []
        warnings = []
        
        # Validate description
        if not data.description or len(data.description.strip()) < 5:
            errors.append("Description is too short")
        
        # Validate alert radius
        if data.alert_radius < 1:
            data.alert_radius = 2
            warnings.append("Alert radius set to minimum (2km)")
        elif data.alert_radius > 1000:
            data.alert_radius = 1000
            warnings.append("Alert radius capped at maximum (1000km)")
        
        # Validate tags
        if not data.tags or len(data.tags) == 0:
            if data.confidence_score > 0.5:
                errors.append("No services could be identified")
            else:
                warnings.append("Services unclear - may need clarification")
        elif len(data.tags) > 20:
            data.tags = data.tags[:20]
            warnings.append("Too many tags - limited to first 20")
        
        # Validate provider
        if data.provider is None and data.confidence_score > 0.6:
            errors.append("Cannot determine if offering or seeking services")
        
        # Validate expiry
        if data.expiry != "never":
            try:
                expiry_dt = datetime.fromisoformat(data.expiry.replace('Z', '+00:00'))
                if expiry_dt <= datetime.now(expiry_dt.tzinfo):
                    errors.append("Expiry date is in the past")
            except (ValueError, AttributeError):
                warnings.append("Expiry date format unclear - using default")
                default_expiry = datetime.now() + timedelta(days=7)
                data.expiry = default_expiry.isoformat() + "Z"
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "data": data
        }

class WhistleAgent:
    """-grade whistle agent with advanced LLM processing"""
    
    def __init__(self, mcp: FastMCP):
        self.mcp = mcp
        self.llm_extractor = AdvancedLLMExtractor()
        self.validator = WhistleValidator()
        self.register_tools()
    
    def register_tools(self):
        @self.mcp.tool()
        async def create_whistle(
            user_input: Annotated[
                str, 
                Field(
                    description="""Natural language input describing any service request or offer.
                    
                    The system uses advanced AI to understand:
                    - Any type of service, skill, or help needed/offered
                    - Whether you're providing or seeking services
                    - Location preferences and timing
                    - Context and intent from conversational input
                    
                    Examples of what works:
                    - "I need someone to fix my leaky faucet"
                    - "Can teach piano lessons to beginners"
                    - "Looking for a babysitter this weekend"
                    - "Available for freelance graphic design work"
                    - "Need help moving furniture tomorrow"
                    - "Offering Spanish conversation practice"
                    
                    Just describe what you need or can offer naturally."""
                )
            ],
            access_token: Annotated[
                str,
                Field(description="User authentication token", default="")
            ] = "",
            confidence_threshold: Annotated[
                float,
                Field(
                    description="Minimum confidence score to proceed (0.0-1.0)",
                    default=0.6,
                    ge=0.0,
                    le=1.0
                )
            ] = 0.6,
            force_create: Annotated[
                bool,
                Field(
                    description="Force creation even with low confidence",
                    default=False
                )
            ] = False
        ) -> Dict[str, Any]:
            """
            Create a whistle from any natural language input using advanced AI processing.
            
            This tool uses sophisticated language understanding to extract service information
            from conversational input without relying on keywords or patterns.
            
            Returns:
            - success: Whistle created successfully
            - clarification_needed: More information required
            - error: Creation failed
            """
            try:                
                
                # Extract attributes using OpenAI
                extracted_data = await self.llm_extractor.extract_attributes(user_input)
                
                # Validate extracted data
                validation_result = self.validator.validate_whistle_data(extracted_data)
                
                # Check confidence and validation
                needs_clarification = (
                    extracted_data.ask_again or 
                    not validation_result["valid"] or 
                    (extracted_data.confidence_score < confidence_threshold and not force_create)
                )
                
                if needs_clarification:
                    return {
                        "status": ProcessingStatus.CLARIFICATION_NEEDED.value,
                        "message": extracted_data.reason or "; ".join(validation_result["errors"]),
                        "confidence_score": extracted_data.confidence_score,
                        "extracted_data": {
                            "description": extracted_data.description,
                            "tags": extracted_data.tags,
                            "provider": extracted_data.provider,
                            "alertRadius": extracted_data.alert_radius,
                            "expiry": extracted_data.expiry
                        },
                        "warnings": validation_result.get("warnings", []),
                        "suggestions": self._generate_dynamic_suggestions(extracted_data, validation_result)
                    }
                
                # Prepare whistle data for API
                whistle_data = {
                    "description": extracted_data.description,
                    "alertRadius": extracted_data.alert_radius,
                    "tags": extracted_data.tags,
                    "provider": extracted_data.provider if extracted_data.provider is not None else False,
                    "expiry": extracted_data.expiry
                }
                
                logger.info("Creating whistle", whistle_data=whistle_data, confidence=extracted_data.confidence_score)
                
                print("whistle_data",whistle_data)
                # Create whistle via API
                result = await api_client.request(
                    method="POST",
                    endpoint="/whistle",
                    data={"whistle": whistle_data},
                    headers={"Authorization": access_token}
                )
                
                # Process API response
                new_whistle = result.get("newWhistle")
                if not new_whistle:
                    return {
                        "status": ProcessingStatus.ERROR.value,
                        "message": "Whistle creation failed - no whistle returned"
                    }
                
                # Format response
                formatted_whistle = {
                    "id": new_whistle.get("_id") or new_whistle.get("id"),
                    "description": new_whistle.get("description", ""),
                    "tags": new_whistle.get("tags", []),
                    "alertRadius": new_whistle.get("alertRadius", 2),
                    "expiry": new_whistle.get("expiry", "never"),
                    "provider": new_whistle.get("provider", False),
                    "active": new_whistle.get("active", True),
                }
                
                logger.info(
                    "Whistle created successfully", 
                    whistle_id=formatted_whistle["id"],
                    provider=formatted_whistle["provider"],
                    confidence=extracted_data.confidence_score
                )
                
                return {
                    "status": ProcessingStatus.SUCCESS.value,
                    "whistle": formatted_whistle,
                    "message": f"Whistle created successfully! {'Offering' if formatted_whistle['provider'] else 'Seeking'} {', '.join(formatted_whistle['tags'])}",
                    "confidence_score": extracted_data.confidence_score,
                    "warnings": validation_result.get("warnings", []),
                    "matching_whistles": result.get("matchingWhistles", [])
                }
                
            except Exception as e:
                error_msg = str(e)
                logger.error("Whistle creation failed", error=error_msg)
                
                # Handle specific API errors
                if "ETLIMIT" in error_msg:
                    return {
                        "status": ProcessingStatus.ERROR.value,
                        "message": "Too many tags specified (maximum 20 allowed)"
                    }
                elif "referral" in error_msg.lower():
                    return {
                        "status": ProcessingStatus.ERROR.value,
                        "message": error_msg
                    }
                else:
                    return {
                        "status": ProcessingStatus.ERROR.value,
                        "message": "An unexpected error occurred while creating the whistle. Please try again later."
                    }
    
    
        
        @self.mcp.tool()
        async def list_whistles(
            access_token: Annotated[
                str, Field(description="User authentication token", default="")
            ] = "",
            active_only: Annotated[
                bool,
                Field(
                    description="If True, only return active whistles",
                    default=False
                )
            ] = False
        ) -> Dict[str, Any]:
            """
            Fetch all whistles for the authenticated user.

            Args:
                access_token: User authentication token
                active_only: If True, only return active whistles

            Returns:
                Dictionary with success status and list of whistles
            """
            try:            
               # Fetch user details from the 'user' endpoint
                result = await api_client.request(
                    method="GET",
                    endpoint="/user",
                    headers={"Authorization": access_token}
                )
                print("list_whistles result",result)
                user = result.get("user", {})
                whistles = user.get("Whistles", [])

                # Apply active filter if requested
                if active_only:
                    whistles = [w for w in whistles if w.get("active", True)]

                # Format whistles in a consistent manner
                formatted_whistles = [
                    {
                        "id": w.get("id") or w.get("_id"),
                        "description": w.get("description", ""),
                        "tags": w.get("tags", []),
                        "alertRadius": w.get("alertRadius", 2),
                        "expiry": w.get("expiry", "never"),
                        "provider": w.get("provider", False),
                        "active": w.get("active", True),
                    }
                    for w in whistles
                ]

                logger.info(
                    "Whistles listed successfully",
                    total_count=len(formatted_whistles),
                    active_only=active_only
                )

                return {
                    "status": "success",
                    "whistles": formatted_whistles
                }

            except Exception as e:
                error_msg = str(e)
                logger.error("Whistle listing failed", error=error_msg)

                return {
                    "status": "error",
                    "message": "An unexpected error occurred while creating the whistle. Please try again later.",
                    "whistles": []
                }

    def _generate_dynamic_suggestions(self, data: ExtractedWhistleData, validation_result: Dict[str, Any]) -> List[str]:
        """Generate contextual suggestions based on extraction results"""
        suggestions = []
        
        if data.confidence_score < 0.3:
            suggestions.append("Try rephrasing your request with more specific details about what you need or can offer")
        
        if not data.tags or len(data.tags) == 0:
            suggestions.append("Please specify the type of service more clearly (e.g., 'home repair', 'tutoring', 'delivery')")
        
        if data.provider is None:
            suggestions.append("Clarify whether you're offering a service ('I can...', 'I provide...') or looking for one ('I need...', 'Looking for...')")
        
        if data.confidence_score < 0.5 and data.tags:
            suggestions.append(f"I detected these services: {', '.join(data.tags)}. Is this correct?")
        
        # Add validation-based suggestions
        for error in validation_result.get("errors", []):
            if "services" in error.lower():
                suggestions.append("Try being more specific about the type of help or service involved")
            elif "provider" in error.lower():
                suggestions.append("Make it clearer whether you're offering help or asking for help")
        
        return suggestions

    