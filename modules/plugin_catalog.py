# -*- coding: utf-8 -*-
# This plugins is licensed under the MIT license: http://www.opensource.org/licenses/mit-license.php
# Authors: Kenji Hosoda <hosoda@s-cubism.jp>
from gluon import *
from gluon.storage import Storage

class _BulkLoader(object):
    def __init__(self):
        self.flattened = []
        self.sizes = []
    def register(self, values):
        self.flattened.extend(values)
        self.sizes.append(len(values))
    def load(self, fn):
        self.flattened = fn(self.flattened)
    def retrieve(self):
        size = self.sizes.pop(0)
        objects = self.flattened[:size]
        self.flattened = self.flattened[size:]
        return objects
        
class Catalog(object):
    
    def __init__(self, db):
        self.db = db
        
        settings = self.settings = Storage()
        
        settings.extra_fields = {}
        
        settings.table_product_name = 'catalog_product'
        settings.table_product = None
        
        settings.table_variant_name = 'catalog_variant'
        settings.table_variant = None
        settings.table_variant_orderby = None
        
        settings.table_option_group_name = 'catalog_option_group'
        settings.table_option_group = None
        
        settings.table_option_name = 'catalog_option'
        settings.table_option = None
        self.init_record_pool()
        
    def init_record_pool(self):
        self._option_pool = {}
        self._option_group_pool = {}
        
    def define_tables(self, migrate=True, fake_migrate=False):
        db, settings = self.db, self.settings
        
        if not settings.table_product_name in db.tables:
            table = db.define_table(
                settings.table_product_name,
                *settings.extra_fields.get(settings.table_product_name, []))
        settings.table_product = db[settings.table_product_name]
                
        if not settings.table_variant_name in db.tables:
            table = db.define_table(
                settings.table_variant_name,
                Field('product', 'reference %s' % settings.table_product_name,
                      readable=False, writable=False),
                Field('options', 'list:reference %s' % settings.table_option_name,
                      readable=False, writable=False),
                migrate=migrate, fake_migrate=fake_migrate,
                *settings.extra_fields.get(settings.table_variant_name, []))
            settings.table_variant_orderby = table.id
        settings.table_variant = db[settings.table_variant_name]
                
        if not settings.table_option_group_name in db.tables:
            table = db.define_table(
                settings.table_option_group_name,
                migrate=migrate, fake_migrate=fake_migrate,
                *settings.extra_fields.get(settings.table_option_group_name, []))
        settings.table_option_group = db[settings.table_option_group_name]
        
        if not settings.table_option_name in db.tables:
            table = db.define_table(
                settings.table_option_name,
                Field('option_group', 'reference %s' % settings.table_option_group_name,
                      readable=False, writable=False),
                migrate=migrate, fake_migrate=fake_migrate,
                *settings.extra_fields.get(settings.table_option_name, []))
        settings.table_option = db[settings.table_option_name]
                
    def add_product(self, product_vars, variant_vars_list):
        if not variant_vars_list:
            raise ValueError
        product_id = self.settings.table_product.insert(**product_vars)
        for variant_vars in variant_vars_list:
            self.settings.table_variant.insert(product=product_id, **variant_vars)  
        return product_id
        
    def edit_product(self, product_id, product_vars, variant_vars_list):
        self.db(self.settings.table_product.id==product_id).update(**product_vars)
        table_variant = self.settings.table_variant
        self.db(table_variant.product==product_id).delete()
        for variant_vars in variant_vars_list:
            table_variant.insert(product=product_id, **variant_vars)  
        
    def remove_product(self, product_id):
        self.db(self.settings.table_variant.product==product_id).delete()
        return self.db(self.settings.table_product.id==product_id).delete()
        
    def get_options(self, option_ids):
        return self._get_records(self.settings.table_option, 
                                 option_ids, self._option_pool)
                                 
    def get_option_groups(self, option_group_ids):
        return self._get_records(self.settings.table_option_group, 
                                 option_group_ids, self._option_group_pool)
        
    def _get_records(self, table, ids, pool):
        if not ids:
            return []
        _ids = [e for e in ids if e not in pool]
        if _ids:
            records = self.db(table.id.belongs(set(_ids))).select()
            tablename = str(table)
            pool.update(**dict([(r[tablename].id if tablename in r else r.id, r) for r in records]))
        return [pool[id] for id in ids]
    
    def get_product(self, product_id, load_variants=True, 
                    load_options=True, load_option_groups=True, 
                    variant_fields=[], variant_attributes={},
                    fields=[]):
        settings = self.settings
        product = self.db(settings.table_product.id==product_id).select(*fields).first()
        if not product:
            return None
            
        if load_variants:
            product.variants = self.variants_from_product(product_id
                    ).select(orderby=settings.table_variant_orderby, 
                             *variant_fields, **variant_attributes)
            if load_options:
                for variant in product.variants:
                    variant.options = self.get_options(variant.options)
                product.option_groups = [option.option_group for option 
                        in product.variants and product.variants[0].options or []]
                if load_option_groups:       
                    product.option_groups = self.get_option_groups(product.option_groups)
            
        return product
        
    def products_from_query(self, query, load_variants=True, 
                              load_options=True, load_option_groups=True, 
                              variant_fields=[], variant_attributes={}):
        db, settings, get_options, get_option_groups = self.db, self.settings, self.get_options, self.get_option_groups
        
        class _VirtualSet(object):
        
            def count(self):
                return db(query).count()
                
            def select(self, *fields, **attributes):
                
                table_variant = settings.table_variant
                products = db(query).select(*fields, **attributes)
                
                if not products or not load_variants:
                    return products
                tablename = settings.table_product_name
                joined = (tablename in products[0])
                    
                product_ids = [r[tablename].id if joined else r.id for r in products]
                                 
                from itertools import groupby                               
                variants = db(table_variant.product.belongs(product_ids)
                              ).select(orderby=table_variant.product|settings.table_variant_orderby,
                                       *variant_fields, **variant_attributes)
                _variants = {}
                for k, g in groupby(variants, key=lambda r: r.product):
                    _variants[k] = list(g)
                   
                for r in products:
                    if joined:
                        r[tablename].variants = _variants.get(r[tablename].id, [])
                    else:
                        r.variants = _variants.get(r.id, []) 
                    
                if not load_options:
                    return products
                    
                bulk_loader = _BulkLoader()        
                for r in products:
                    for variant in r[tablename].variants if joined else r.variants:
                        bulk_loader.register(variant.options or [])
                bulk_loader.load(get_options)
                for r in products:
                    for variant in r[tablename].variants if joined else r.variants:
                        variant.options = bulk_loader.retrieve()
                
                if load_option_groups:        
                    bulk_loader = _BulkLoader()
                for r in products:
                    if joined:
                        r[tablename].option_groups = [option.option_group for option 
                                in r[tablename].variants and r[tablename].variants[0].options or []]
                    else:
                        r.option_groups = [option.option_group for option 
                                in r.variants and r.variants[0].options or []]
                    if load_option_groups:
                        bulk_loader.register(r[tablename].option_groups if joined else r.option_groups)
                
                if load_option_groups:
                    bulk_loader.load(get_option_groups)
                    for r in products:
                        if joined:
                            r[tablename].option_groups = bulk_loader.retrieve()
                        else:
                            r.option_groups = bulk_loader.retrieve()
                            
                return products
                
        return _VirtualSet()
        
    def get_variant(self, id=None, sku=None, load_product=True, 
                    load_options=True, load_option_groups=True, 
                    product_fields=[], product_attributes={},
                    fields=[]):
        settings = self.settings
        if id:
            variant = self.db(settings.table_variant.id==id).select(*fields).first()
        elif sku:
            variant = self.db(settings.table_variant.sku==sku).select(*fields).first()
        else:
            return None
        if not variant:
            return None
           
        if load_product:
            variant.product = self.get_product(variant.product, load_variants=False,
                                               *product_fields, **product_attributes)
            if load_options:
                variant.options = self.get_options(variant.options)
                variant.product.option_groups = [option.option_group for option 
                                                    in variant.options or []]
                if load_option_groups:       
                    variant.product.option_groups = self.get_option_groups(variant.product.option_groups)
            
        return variant
        
    def variants_from_product(self, product_id):
        return self.db(self.settings.table_variant.product==product_id)
        
    def options_from_option_group(self, option_group_id):
        return self.db(self.settings.table_option.option_group==option_group_id)
        
    def get_option_sets(self, option_group_ids):
        options_list = [self.options_from_option_group(option_group_id).select()
                        for option_group_id in option_group_ids]
        if not options_list:
            return []
            
        def itertools_product(*args, **kwds): # for python < 2.6
            pools = map(tuple, args) * kwds.get('repeat', 1)
            result = [[]]
            for pool in pools:
                result = [x+[y] for x in result for y in pool]
            for prod in result:
                yield tuple(prod)
                
        return list(itertools_product(*options_list))
       