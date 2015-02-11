# coding: utf-8
from __future__ import unicode_literals

import re
import sre_constants
import itertools

from . import registry


RECURSIVE_REFERENCE_CONSTANT = 'self'


def _validate_regex(regex):
    """
    :type regex: str
    :raises: ValueError
    :return:
    """
    try:
        re.compile(regex)
    except sre_constants.error as e:
        raise ValueError('Invalid regular expression: {}'.format(e))


class BaseField(object):
    def __init__(self, required=False, default=None, choices=None,
                 title=None, description=None):
        self.required = required
        self.title = title
        self.description = description
        self._choices = choices
        self._default = default

    @property
    def choices(self):
        choices = self._choices
        if callable(self._choices):
            choices = self._choices()
        return choices

    @property
    def default(self):
        default = self._default
        if callable(self._default):
            default = self._default()
        return default

    def _get_common_schema_fields(self):
        rv = {}
        if self.title is not None:
            rv['title'] = self.title
        if self.description is not None:
            rv['description'] = self.description
        if self.choices:
            rv['enum'] = list(self.choices)
        if self._default is not None:
            rv['default'] = self.default
        return rv

    def get_definitions_and_schema(self, definitions=None):
        raise NotImplementedError()

    def get_schema(self):
        definitions, schema = self.get_definitions_and_schema()
        if definitions:
            schema['definitions'] = definitions
        return schema

    def walk(self, through_document_fields=False, visited_documents=()):
        yield self


class StringField(BaseField):
    def __init__(self, regex=None, min_length=None, max_length=None, **kwargs):
        self.regex = regex
        if self.regex is not None:
            _validate_regex(self.regex)
        self.max_length = max_length
        self.min_length = min_length
        super(StringField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, definitions=None):
        schema = {'type': 'string'}
        schema.update(self._get_common_schema_fields())
        if self.regex:
            schema['pattern'] = self.regex
        if self.min_length is not None:
            schema['minLength'] = self.min_length
        if self.max_length is not None:
            schema['maxLength'] = self.max_length
        return {}, schema


class BooleanField(BaseField):
    def get_definitions_and_schema(self, definitions=None):
        schema = {'type': 'boolean'}
        schema.update(self._get_common_schema_fields())
        return {}, schema


class EmailField(StringField):
    def get_definitions_and_schema(self, definitions=None):
        definitions, schema = super(EmailField, self).get_definitions_and_schema(definitions=definitions)
        schema['format'] = 'email'
        return definitions, schema


class IPv4Type(StringField):
    def get_definitions_and_schema(self, definitions=None):
        definitions, schema = super(IPv4Type, self).get_definitions_and_schema(definitions=definitions)
        schema['format'] = 'ipv4'
        return definitions, schema


class DateTimeField(StringField):
    def get_definitions_and_schema(self, definitions=None):
        definitions, schema = super(DateTimeField, self).get_definitions_and_schema(definitions=definitions)
        schema['format'] = 'date-time'
        return definitions, schema


class UriField(StringField):
    def get_definitions_and_schema(self, definitions=None):
        definitions, schema = super(UriField, self).get_definitions_and_schema(definitions=definitions)
        schema['format'] = 'uri'
        return definitions, schema


# http://python-jsonschema.readthedocs.org/en/latest/validate/
# TODO: ipv6


class NumberField(BaseField):
    _NUMBER_TYPE = 'number'

    def __init__(self, multiple_of=None, minimum=None, maximum=None,
                 exclusive_minimum=False, exclusive_maximum=False, **kwargs):
        self.multiple_of = multiple_of
        self.minimum = minimum
        self.exclusive_minimum = exclusive_minimum
        self.maximum = maximum
        self.exclusive_maximum = exclusive_maximum
        super(NumberField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, definitions=None):
        schema = {'type': self._NUMBER_TYPE}
        schema.update(self._get_common_schema_fields())
        if self.multiple_of is not None:
            schema['multipleOf'] = self.multiple_of
        if self.minimum is not None:
            schema['minimum'] = self.minimum
        if self.exclusive_minimum:
            schema['exclusiveMinumum'] = True
        if self.maximum is not None:
            schema['maximum'] = self.maximum
        if self.exclusive_maximum:
            schema['exclusiveMaximum'] = True
        return {}, schema


class IntField(NumberField):
    _NUMBER_TYPE = 'integer'


class ArrayField(BaseField):
    def __init__(self, items, min_items=None, max_items=None, unique_items=False,
                 additional_items=None, **kwargs):
        self.items = items
        self.min_items = min_items
        self.max_items = max_items
        self.unique_items = unique_items
        self.additional_items = additional_items
        super(ArrayField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, definitions=None):
        if isinstance(self.items, (list, tuple)):
            nested_definitions = {}
            nested_schema = []
            for item in self.items:
                item_definitions, item_schema = item.get_definitions_and_schema(
                    definitions=definitions)
                nested_definitions.update(item_definitions)
                nested_schema.append(item_schema)
        else:
            nested_definitions, nested_schema = self.items.get_definitions_and_schema(
                definitions=definitions)
        schema = {
            'type': 'array',
            'items': nested_schema,
        }
        schema.update(self._get_common_schema_fields())
        if self.min_items is not None:
            schema['minItems'] = self.min_items
        if self.max_items is not None:
            schema['maxItems'] = self.max_items
        if self.unique_items:
            schema['uniqueItems'] = True

        if self.additional_items is not None:
            if isinstance(self.additional_items, bool):
                schema['additionalItems'] = self.additional_items
            else:
                items_definitions, items_schema = self.additional_items.get_definitions_and_schema(
                    definitions=definitions)
                schema['additionalItems'] = items_schema
                nested_definitions.update(items_definitions)

        return nested_definitions, schema

    def walk(self, through_document_fields=False, visited_documents=()):
        yield self
        if isinstance(self.items, (list, tuple)):
            for field in self.items:
                for field_ in field.walk(through_document_fields=through_document_fields,
                                         visited_documents=visited_documents):
                    yield field_
        else:
            for field in self.items.walk(through_document_fields=through_document_fields,
                                         visited_documents=visited_documents):
                yield field


class DictField(BaseField):
    # max_properties
    def __init__(self, properties=None, pattern_properties=None, additional_properties=None,
                 min_properties=None, max_properties=None, **kwargs):
        self.properties = properties
        self.pattern_properties = pattern_properties
        self.additional_properties = additional_properties
        self.min_properties = min_properties
        self.max_properties = max_properties
        super(DictField, self).__init__(**kwargs)

    @staticmethod
    def _process_properties(properties, definitions=None):
        nested_definitions = {}
        schema = {}
        for prop, field in properties.iteritems():
            field_definitions, field_schema = field.get_definitions_and_schema(
                definitions=definitions)
            schema[prop] = field_schema
            nested_definitions.update(field_definitions)
        return nested_definitions, schema

    def get_definitions_and_schema(self, definitions=None):
        nested_definitions = {}
        schema = {'type': 'object'}
        schema.update(self._get_common_schema_fields())

        if self.properties is not None:
            properties_definitions, properties_schema = self._process_properties(
                self.properties, definitions=definitions)
            schema['properties'] = properties_schema
            nested_definitions.update(properties_definitions)

        if self.pattern_properties is not None:
            for key in self.pattern_properties.iterkeys():
                _validate_regex(key)
            properties_definitions, properties_schema = self._process_properties(
                self.pattern_properties, definitions=definitions)
            schema['patternProperties'] = properties_schema
            nested_definitions.update(properties_definitions)

        if self.additional_properties is not None:
            if isinstance(self.additional_properties, bool):
                schema['additionalProperties'] = self.additional_properties
            else:
                properties_definitions, properties_schema = self.additional_properties.get_definitions_and_schema(
                    definitions=definitions)
                schema['additionalProperties'] = properties_schema
                nested_definitions.update(properties_definitions)

        if self.min_properties is not None:
            schema['minProperties'] = self.min_properties
        if self.max_properties is not None:
            schema['maxProperties'] = self.max_properties

        return nested_definitions, schema

    def walk(self, through_document_fields=False, visited_documents=()):
        fields_to_visit = []
        if self.properties is not None:
            fields_to_visit.append(self.properties.itervalues())
        if self.pattern_properties is not None:
            fields_to_visit.append(self.pattern_properties.itervalues())
        if self.additional_properties is not None and not isinstance(self.additional_properties, bool):
            fields_to_visit.append([self.additional_properties])

        yield self
        for field in itertools.chain(*fields_to_visit):
            for field_ in field.walk(through_document_fields=through_document_fields,
                                     visited_documents=visited_documents):
                yield field_


class DocumentField(BaseField):
    def __init__(self, document_cls, **kwargs):
        self._document_cls = document_cls
        self.owner_cls = None
        super(DocumentField, self).__init__(**kwargs)

    def walk(self, through_document_fields=False, visited_documents=()):
        yield self
        if through_document_fields and self.document_cls not in visited_documents:
            for field in self.document_cls.walk(through_document_fields=through_document_fields,
                                                visited_documents=visited_documents + (self.document_cls,)):
                yield field

    def get_definitions_and_schema(self, definitions=None):
        definition_id = self.document_cls.get_definition_id()
        if definitions and definition_id in definitions:
            return {}, definitions[definition_id]
        else:
            return self.document_cls.get_definitions_and_schema(definitions=definitions)

    def set_owner(self, owner_cls):
        self.owner_cls = owner_cls

    @property
    def document_cls(self):
        if isinstance(self._document_cls, basestring):
            if self._document_cls == RECURSIVE_REFERENCE_CONSTANT:
                if self.owner_cls is None:
                    raise ValueError('owner_cls is not set')
                return self.owner_cls
            else:
                try:
                    return registry.get_document(self._document_cls)
                except KeyError:
                    if self.owner_cls is None:
                        raise ValueError('owner_cls is not set')
                    return registry.get_document(self._document_cls, module=self.owner_cls.__module__)
        else:
            return self._document_cls


class OfField(BaseField):
    _KEYWORD = None

    def __init__(self, fields, **kwargs):
        self.fields = list(fields)
        super(OfField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, definitions=None):
        nested_definitions = {}
        one_of = []
        for field in self.fields:
            field_definitions, field_schema = field.get_definitions_and_schema(definitions=definitions)
            nested_definitions.update(field_definitions)
            one_of.append(field_schema)
        schema = {self._KEYWORD: one_of}
        schema.update(self._get_common_schema_fields())
        return nested_definitions, schema

    def walk(self, through_document_fields=False, visited_documents=()):
        yield self
        for field in self.fields:
            for field_ in field.walk(through_document_fields=through_document_fields,
                                     visited_documents=visited_documents):
                yield field_


class OneOfField(OfField):
    _KEYWORD = 'oneOf'


class AnyOfField(OfField):
    _KEYWORD = 'anyOf'


class AllOfField(OfField):
    _KEYWORD = 'allOf'


class NotField(BaseField):
    def __init__(self, field, **kwargs):
        self.field = field
        super(NotField, self).__init__(**kwargs)

    def get_definitions_and_schema(self, definitions=None):
        field_definitions, field_schema = self.field.get_definitions_and_schema(
            definitions=definitions)
        schema = {'not': field_schema}
        schema.update(self._get_common_schema_fields())
        return field_definitions, schema