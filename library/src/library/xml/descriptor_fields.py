"""
Descriptor-based field system for XMLDocument.

All descriptors read from / write to `instance._elem` (an lxml _Element).

Field types
-----------
AttrField        – XML attribute on the element itself
ChildTextField   – text content of a direct child element
TextField        – text content of the element itself
ChildField       – single nested XMLDocument model
ChildListField   – list of nested XMLDocument models
"""

from typing import Type, TypeVar, Any
from lxml import etree

T = TypeVar("T")


def _clark(tag: str, ns: str | None) -> str:
    """Return Clark-notation tag: {ns}tag or just tag."""
    return f"{{{ns}}}{tag}" if ns else tag


class AttrField:
    """
    Maps to an XML attribute of *the element itself*.

    Parameters
    ----------
    name    : XML attribute name (e.g. "id", "media-type", "playOrder")
    ns      : optional namespace URI (e.g. XML_NS for xml:lang)
    default : value returned when the attribute is absent
    type    : type to convert the attribute value to (default: str)
    """

    def __init__(self, name: str, ns: str | None = None, default: Any = None, type: Type = str):
        self.clark = _clark(name, ns)
        self.default = default
        self.attr_name = ""  # set by __set_name__
        self.type = type

    def __set_name__(self, owner, name):
        self.attr_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        val = instance._elem.get(self.clark, self.default)
        if val is self.default:
            return val
        return self.type(val)

    def __set__(self, instance, value):
        if value is None:
            instance._elem.attrib.pop(self.clark, None)
        else:
            instance._elem.set(self.clark, str(value))


class TextField:
    """
    Maps to the text content (.text) of the element itself.
    """

    def __init__(self, default: Any = None):
        self.default = default
        self.attr_name = ""

    def __set_name__(self, owner, name):
        self.attr_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        text = instance._elem.text
        return text if text is not None else self.default

    def __set__(self, instance, value):
        instance._elem.text = str(value) if value is not None else None


class ChildTextField:
    """
    Maps to the text content of a *direct child* element.

    Parameters
    ----------
    tag     : local tag name of the child
    ns      : namespace URI for the child tag
    default : returned when child is absent or has no text
    """

    def __init__(self, tag: str, ns: str | None = None, default: Any = None):
        self.clark = _clark(tag, ns)
        self.tag = tag
        self.ns = ns
        self.default = default
        self.attr_name = ""

    def __set_name__(self, owner, name):
        self.attr_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        child = instance._elem.find(self.clark)
        if child is None:
            return self.default
        return child.text if child.text is not None else self.default

    def __set__(self, instance, value):
        child = instance._elem.find(self.clark)
        if value is None:
            if child is not None:
                instance._elem.remove(child)
            return
        if child is None:
            child = etree.SubElement(instance._elem, self.clark)
        child.text = str(value)


class ChildField:
    """
    Maps to a single nested XMLDocument model (direct child element).

    Parameters
    ----------
    model_cls : XMLDocument subclass used to wrap the found element
    tag       : local tag name (defaults to model_cls.__tag__)
    ns        : namespace URI (defaults to model_cls.__ns__)
    default   : returned when child is absent; typically None
    """

    def __init__(self, model_cls: Type[T], tag: str | None = None, ns: str | None = None, default: Any = None):
        self._model_cls = model_cls
        self._tag = tag
        self._ns = ns
        self.default = default
        self.attr_name = ""

    def __set_name__(self, owner, name):
        self.attr_name = name

    def _clark(self, model_cls) -> str:
        tag = self._tag or model_cls.__tag__
        ns = self._ns if self._ns is not None else model_cls.__ns__
        return _clark(tag, ns)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        clark = self._clark(self._model_cls)
        child = instance._elem.find(clark)
        if child is None:
            return self.default
        return self._model_cls(child)

    def __set__(self, instance, value):
        clark = self._clark(self._model_cls)
        old = instance._elem.find(clark)
        if value is None:
            if old is not None:
                instance._elem.remove(old)
            return
        new_elem = value._elem if hasattr(value, "_elem") else value
        if old is not None:
            old.getparent().replace(old, new_elem)
        else:
            instance._elem.append(new_elem)


class ChildListField:
    """
    Maps to a list of nested XMLDocument models (all direct children with matching tag).

    Parameters
    ----------
    model_cls : XMLDocument subclass
    tag       : local tag name (defaults to model_cls.__tag__)
    ns        : namespace URI (defaults to model_cls.__ns__)
    """

    def __init__(self, model_cls: Type[T], tag: str | None = None, ns: str | None = None):
        self._model_cls = model_cls
        self._tag = tag
        self._ns = ns
        self.attr_name = ""

    def __set_name__(self, owner, name):
        self.attr_name = name

    def _clark(self) -> str:
        tag = self._tag or self._model_cls.__tag__
        ns = self._ns if self._ns is not None else self._model_cls.__ns__
        return _clark(tag, ns)

    def __get__(self, instance, owner) -> list[T]:
        if instance is None:
            return self
        clark = self._clark()
        return [self._model_cls(child) for child in instance._elem.findall(clark)]

    def __set__(self, instance, values: list[T]):
        clark = self._clark()
        for old in instance._elem.findall(clark):
            instance._elem.remove(old)
        for v in values:
            new_elem = v._elem if hasattr(v, "_elem") else v
            instance._elem.append(new_elem)
