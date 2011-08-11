# -*- coding: utf-8 -*-
from plugin_suggest_widget import suggest_widget

db = DAL('sqlite:memory:') 
db.define_table('category',Field('name'))
db.define_table('product', 
    Field('category_1'),
    Field('category_2', db.category),
    )
db.category.bulk_insert([{'name':'Alex'}, {'name':'Alice'}, {'name':'John'}, {'name':'Tim'},
                         {'name':'Tom'},{'name':'Joseph'},{'name':'Ben'},{'name':'Bob'}])
db.product.category_1.widget = suggest_widget(
    request, db.category.name, limitby=(0,10), min_length=1)

db.product.category_2.widget = suggest_widget(
    request, db.category.name, id_field=db.category.id, limitby=(0,10), min_length=1) 
     
def index():
    form = SQLFORM(db.product)
    if form.accepts(request.vars, session):
        session.flash = 'submitted : {category_1: %s category_2: %s}' % (form.vars.category_1, form.vars.category_2)
        redirect(URL('index'))
    return dict(form=form, categories=SQLTABLE(db().select(db.category.ALL)))