from copy import deepcopy
from functools import wraps
from itertools import count

from django.db.models.query import QuerySet, BaseIterable

VERSION = (0, 2, 2)
__all__ = ['NV', 'model_fields_map']
__title__ = 'DjangoNestedValues'
__version__ = '.'.join(map(str, VERSION if VERSION[-1] else VERSION[:2]))
__author__ = 'Klimenko Artyem'
__contact__ = 'aklim007@gmail.com'
__homepage__ = 'https://github.com/aklim007/DjangoNestedValues'
__copyright__ = 'Клименко Артём <aklim007@gmail.com>'


def model_fields_map(model, fields=None, exclude=None, prefix='', prefixm='', attname=True, rename=None):
    """
    На основании переданной модели, возвращает список tuple, содержащих путь в орм к этому полю,
    и с каким именем оно должно войти в результат.
    Обрабатываются только обычные поля, m2m и generic сюда не войдут.
    ARGUMENTS:
        :param model: модель или инстанс модели на основе которой будет формироваться список полей
        :param None | collections.Container fields: список полей которые будут забраны из модели
        :param None | collections.Container exclude: список полей которые не будут забираться
        :param str prefix: ORM путь по которому будут распологаться модель в запросе
        :param str prefixm: префикс который будет добавлен к имени поля
        :param bool attname: использовать имя name (model) или attname(model_id) эти поля отличаются для внешних ключей
        :param dict rename: словарь переименования полей
        :rtype: list[tuple[str]]
    """
    data = []
    rename = rename or {}
    attribute = 'attname' if attname else 'name'
    for f in model._meta.concrete_fields:
        if fields and f.attname not in fields and f.name not in fields:
            continue
        if exclude and f.attname in exclude and f.name not in exclude:
            continue
        param_name = getattr(f, attribute)
        new_param_name = rename[param_name] if param_name in rename else param_name
        data.append(('{}{}'.format(prefix, param_name), '{}{}'.format(prefixm, new_param_name)))
    return data


class NV(object):
    __slots__ = ('_fieldsmap', '_nest', '_values_list', '_lfieldsmap', '_parent', '_c', 'ifnone')

    def __init__(self, fieldsmap, nest=None, ifnone=None):
        """
        ARGUMENTS:
            :type fieldsmap: list[tuple[str]]
            :type nest: nest None | dict[str, list[tuple[str]] | NV]
            :type ifnone: None | str
        """
        self._fieldsmap = fieldsmap
        #: :type: list[tuple]
        self._lfieldsmap = []
        #: :type: dict[str, NV | list[tuple[str]]]
        self._nest = nest or {}
        self._values_list = None
        #: :type: None | NV
        self._parent = None
        self._c = None
        self.ifnone = ifnone

        for key, nest in self._nest.items():
            if not isinstance(nest, NV):
                self._nest[key] = NV(fieldsmap=nest)
            self._nest[key]._parent = self

    def _parse_value(self, value):
        """
        ARGUMENTS:
            :type value: tuple
            :rtype: dict
        """
        lv = {}
        for newkey, indx in self._lfieldsmap:
            lv[newkey] = value[indx]
        if self.ifnone is not None and lv[self.ifnone] is None:
            return None
        for key, nest in self._nest.items():
            lv[key] = nest._parse_value(value)
        return lv

    @property
    def values_list(self):
        """
        Возвращает cписок полей (могут повторятся), таких каими их требуется скормить для values_list orm
        ARGUMENTS:
            :rtype: list[str]
        """
        if self._values_list is not None:
            return self._values_list
        for indx, key in enumerate(self._fieldsmap):
            if isinstance(key, str):
                self._fieldsmap[indx] = (key, key)
        self._c = count() if self._parent is None else self._parent._c
        v = [key[0] for key in self._fieldsmap]
        self._lfieldsmap = [(key[1], next(self._c)) for key in self._fieldsmap]
        for nest in self._nest.values():
            v += nest.values_list
        self._values_list = v
        return self._values_list


class NestedValuesIterable(BaseIterable):
    """
    Итератор который собственно и вернёт значения в нужном формате
    """

    def __iter__(self):
        queryset = self.queryset
        query = queryset.query
        compiler = query.get_compiler(queryset.db)
        _parse_value = queryset._nested_values._parse_value
        _lfieldsmap = queryset._nested_values._lfieldsmap
        values_list = queryset._nested_values.values_list
        if not query.extra_select and not query.annotation_select:
            for row in compiler.results_iter():
                yield _parse_value(row)
        else:
            field_names = list(query.values_select)
            extra_names = list(query.extra_select)
            afields = list(query.annotation_select)

            correction = len(extra_names)
            fnames_len = len(field_names)
            afields_start = correction + fnames_len
            for indx, v in enumerate(values_list):
                key, position = _lfieldsmap[indx]
                if v in query.annotation_select:
                    correction -= 1
                    position = afields_start + afields.index(v)
                else:
                    position += correction
                _lfieldsmap[indx] = key, position
            for row in compiler.results_iter():
                yield _parse_value(row)


def _clone(self, **kwargs):
    query = self.query.clone()
    if self._sticky_filter:
        query.filter_is_sticky = True
    clone = self.__class__(model=self.model, query=query, using=self._db, hints=self._hints)
    clone._for_write = self._for_write
    clone._prefetch_related_lookups = self._prefetch_related_lookups[:]
    clone._known_related_objects = self._known_related_objects
    clone._iterable_class = self._iterable_class
    clone._fields = self._fields

    clone.__dict__.update(kwargs)
    return clone


def clone_wrapper(old_obj: QuerySet):
    """
    Деоратор функции QuerySet._clone для копирования _nested_values
    Организовано так, что будет патчится только QuerySet на котором был вызван nested_values
    На вход принимаем именно объект, а не функцию, так как на данный момент метод класса уже прикреплён
    к конкретному экземпляру класса.
    """
    # запоминаем исходную функцию копирования, для переданного экземпляра
    _clone = old_obj._clone

    @wraps(_clone)
    def wrapper(**kwargs):
        new_obj = _clone(**kwargs)
        # в новый объект переносим копию _nested_values
        new_obj._nested_values = deepcopy(getattr(old_obj, '_nested_values', None))
        # и также патчим функцию копирования
        new_obj._clone = clone_wrapper(new_obj)
        return new_obj
    return wrapper


def _nested_values(self, fieldsmap, nest=None) -> QuerySet:
    nv = NV(fieldsmap=fieldsmap, nest=nest)
    clone = self._values(*nv.values_list)
    clone._iterable_class = NestedValuesIterable
    clone._nested_values = nv
    clone._clone = clone_wrapper(clone)
    return clone


def setup():
    """Инициализируем модуль"""
    QuerySet.nested_values = _nested_values
