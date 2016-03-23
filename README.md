# DjangoNestedValues

## Requirements

- Python >= 3.4
- Django >= 1.9

## Установка

На текущий момент единственный вариант это скопировать файл с кодом в проект и вызвать setup().

    from app import nestedvalues
    nestedvalues.setup()

## Использование

После установки у QuerySet появляется метод nested_values.

Если кратко:
- values позволяет получить в результате запроса не экземпляр модели, а словарь
- nested_values позволяет получить вложенные словари.

Пример:

    class Status(models.Model):
        name = models.CharField(max_length=255)
    
    
    class Model2(models.Model):
        name = models.CharField(max_length=255)
        param_1 = models.BooleanField(default=True)
        status = models.ForeignKey(Status)
        date_start = models.DateTimeField()
    
    
    class Model3(models.Model):
        name = models.CharField(max_length=255)
        param_1 = models.BooleanField(default=True)
        model2 = models.ForeignKey(Model2)


    result = Model3.objects.all().nested_values(
        fieldsmap=model_fields_map(
            Model3,
            fields={'id', 'param_1'}
        ) + [('model2__status__name', 'status')],
        nest={
            'nest_model': model_fields_map(Model2, prefix='model2__')
        }
    ).first()
    
    >>> pprint(result)
    {'id': 1,
     'nest_model': {'date_start': datetime.datetime(2016, 3, 20, 15, 18, 19, 839941, tzinfo=<UTC>),
                    'id': 1,
                    'name': 'name1',
                    'param_1': False,
                    'status_id': 1},
     'param_1': True,
     'status': 'Ok'}


model\_fields\_map - является функцией помощником, на основании переданных аргументов формируется список ('путь в орм', 'имя ключа в итоговом словаре'), при желании данный список можно сформировать самому.

model\_fields\_map(model, fields=None, exclude=None, prefix='', attname=True, rename=None)
- model - модель DjangoORM
- fields - набор полей, которые нужны в данной модели, можно указывать, как attrname так и name(данные поля отличаются для внешних ключей), при фильтрации полей модели будет происходить проверка на вхождение **in**(переданный объект должен поддерживать это).
- exclude - набор полей, которые не нужны в данной модели, остальное аналогично fields.
- prefix - префикс пути в DjangoORM.
- attname - использовать в качестве имени attrname или name.
- rename - словарь для переименования полей.

Сам nested_values принимает 2 аргумента (fieldsmap, nest=None)
- список tuple описанный выше.
- nest - словарь для описания вложенных объектов, в качестве ключа выступает имя вложенного объекта в итоговом словаре, в качестве значения может быть, как список аналогичный возвращаемому model\_fields\_map, так и экземпляр класса NV(он также может содержать вложенные объекты).

Класс NV при создании принимает аргументы (fieldsmap, nest=None) - аналогичные вышеописанным и отдельный аргумент ifnone, в нём можно указать имя ключа в словаре, который описывает текущий класс, и если значение по этому атрибуту будет равно None, то вместо текущего словаря будет возвращено значение None. Это необходимо чтобы не генерировать словари целиком состоящие из None, что запросто может случиться если внешние ключи допускают NULL.


## TODO

- Предусмотреть возможность генерации не только вложенных словарей, но и списка вложенных словарей, в случае отношений M2M или обратных связей.
- При использовании model\_fields\_map добавить проверку, что все поля указанные в fields, exclude, rename являются действительными, это позволит избежать непредвиденного поведения, когда ошибся при наборе поля, или указано поле, которого уже не существует.
- Тесты =(