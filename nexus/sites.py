# Core site concept heavily inspired by django.contrib.sites

from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext, Context
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.utils.functional import update_wrapper

import os.path

NEXUS_ROOT = os.path.dirname(__file__)

class NexusSite(object):
    _registry = {}

    def register(self, module, namespace=None):
        if callable(module):
            module = module()
        module.site = self
        if not namespace:
            namespace = hash(module)
        self._registry[namespace] = module

    def get_urls(self):
        from django.conf.urls.defaults import patterns, url, include

        urlpatterns = patterns('',
            url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {
                'document_root': os.path.join(NEXUS_ROOT, 'media'),
                'show_indexes': True,
            }, name='nexus-media'),

            url(r'^$', self.as_view(self.dashboard), name='nexus'),
            url(r'^login/$', self.login, name='nexus-login'),
            url(r'^logout/$', self.as_view(self.logout), name='nexus-logout'),
        )
        for namespace, module in self._registry.iteritems():
            urlpatterns += patterns('',
                url(r'^%s/' % namespace, include(module.get_urls())),
            )
        
        return urlpatterns

    urls = property(get_urls)

    def has_permission(self, request):
        """
        Returns True if the given HttpRequest has permission to view
        *at least one* page in the admin site.
        """
        return request.user.is_active and request.user.is_staff

    def as_view(self, view, cacheable=False):
        "Wraps a view in authentication/caching logic"
        def inner(request, *args, **kwargs):
            if not self.has_permission(request):
                # show login pane
                return self.login(request, *args, **kwargs)
            return view(request, *args, **kwargs)

        # Mark it as never_cache
        if not cacheable:
            inner = never_cache(inner)

        # We add csrf_protect here so this function can be used as a utility
        # function for any view, without having to repeat 'csrf_protect'.
        if not getattr(view, 'csrf_exempt', False):
            inner = csrf_protect(inner)

        return update_wrapper(inner, view)

    def render_to_response(self, template, context={}, request=None):
        "Shortcut for rendering to response and default context instances"
        if request:
            context_instance = RequestContext(request)
        else:
            context_instance = Context()
        
        if request:
            context['request'] = request
            context.update(csrf(request))
        
        return render_to_response(template, context,
            context_instance=context_instance
        )

    ## Our views

    def login(self, request):
        "Login form"
        from django.contrib.auth import login as login_
        from django.contrib.auth.forms import AuthenticationForm

        if request.POST:
            form = AuthenticationForm(request, request.POST)
            if form.is_valid():
                login_(request, form.get_user())
                return HttpResponseRedirect(request.POST.get('next') or reverse('nexus'))
            else:
                request.session.set_test_cookie()
        else:
            form = AuthenticationForm(request)
            request.session.set_test_cookie()

        return self.render_to_response('nexus/login.html', {
            'form': form,
        }, request)
    login = never_cache(login)
    
    def logout(self, request):
        "Logs out user and redirects them to Nexus home"
        from django.contrib.auth import logout

        logout(request)

        return HttpResponseRedirect(reverse('nexus'))

    def dashboard(self, request):
        "Basic dashboard panel"
        # TODO: these should be ajax
        module_set = []
        link_set = []
        for module in self._registry.itervalues():
            if hasattr(module, 'render_on_dashboard'):
                module_set.append((module.get_dashboard_title(), module.render_on_dashboard(request)))
            if module.home_url:
                link_set.append((module.get_title(), reverse(module.home_url)))
        
        return self.render_to_response('nexus/dashboard.html', {
            'module_set': module_set,
            'link_set': link_set,
        }, request)

# setup the default site

site = NexusSite()

