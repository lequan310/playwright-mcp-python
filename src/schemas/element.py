from typing import Optional, Union

from pydantic import BaseModel, Field


class AriaLabel(BaseModel):
    role: str = Field(
        ..., description="ARIA role of the element (e.g., 'button', 'link', 'textbox')"
    )
    name: str = Field(..., description="Accessible name of the element (from snapshot)")


class Selector(BaseModel):
    selector: str = Field(
        ..., description="CSS/XPath selector to uniquely identify the element"
    )


# Union type for element locators
ElementLocator = Union[AriaLabel, Selector]


class FormField(BaseModel):
    """Form field definition for filling forms"""

    element: str = Field(..., description="Human-readable element description")
    value: str = Field(..., description="Value to fill in the field")
    locator: ElementLocator = Field(
        ..., description="Element locator (AriaLabel or Selector)"
    )
    nth: Optional[int] = Field(
        None, description="Zero-based index when multiple elements match"
    )
