import os
import re
import threading
import sublime
import sublime_plugin


class CFinderCommand(sublime_plugin.TextCommand):
    result_list = []

    def run(self, edit):
        # Search starts from the file itself.
        current_file = self.view.file_name().split('/').pop()
        headers = [current_file]

        # Get Include PATH, now only support *nix systems.
        current_path = [os.path.dirname(self.view.file_name())]
        try:
            opened_folder = self.view.window().folders()[0] + '/'
        except IndexError:
            opened_folder = '.'
        user_path = [opened_folder + name for name in os.listdir(opened_folder)
                     if os.path.isdir(os.path.join(opened_folder, name))]
        search_path = list(set(current_path + user_path))

        # Take the word selected by user as keyword to search.
        keywords = []
        sels = self.view.sel()
        if not sels:
            return
        for sel in sels:
            keywords.append(self.view.substr(sel))

        threads = []
        thread = KeywordSearch(keywords, headers, search_path)
        threads.append(thread)
        thread.start()

        self.handle_threads(edit, threads)

    def handle_threads(self, edit, threads):
        next_threads = []
        for thread in threads:
            if thread.is_alive():
                next_threads.append(thread)
                continue
            if len(thread.result_list):
                self.result_list = thread.result_list

        threads = next_threads

        if len(threads):
            sublime.set_timeout(
                lambda: self.handle_threads(edit, threads),
                100)
            return

        self.view.sel().clear()
        current_window = self.view.window()
        current_window.show_quick_panel(self.result_list, self.open_selected)

    def open_selected(self, index):
        if index == -1:
            self.result_list[:] = []
            return
        header_info = self.result_list[index].split(';')
        header_file = '{0}:{1}'.format(header_info[0], header_info[1])
        self.view.window().open_file(header_file, sublime.ENCODED_POSITION)
        self.result_list[:] = []


class KeywordSearch(threading.Thread):
    def __init__(self, keywords, headers, search_path):
        self.keywords = keywords
        self.headers = headers
        self.search_path = search_path
        self.result_list = []
        self.searched_header_list = []
        self.header_pattern = re.compile(r'#include\s*["<]([^"]*)[">]')

        threading.Thread.__init__(self)

    def run(self):
        for keyword in self.keywords:
            if not keyword:
                continue
            pattern = re.compile(r'\b{0}\b'.format(keyword))
            self.search(list(set(self.headers)), pattern, keyword)

    def get_func_pattern(self, keyword):
        return re.compile(r'{0}\s*\([\w\s\*,&]*\)'.format(keyword))

    def get_return_value_pattern(self, keyword):
        return re.compile(r'{0}\s*[\*)]'.format(keyword))

    def get_return_pattern(self, keyword):
        return re.compile(r'return\s+{0}'.format(keyword))

    def search(self, headers, pattern, keyword):
        next_headers = []
        for header in headers:
            func_pattern = self.get_func_pattern(keyword)
            return_value_pattern = self.get_return_value_pattern(keyword)
            return_pattern = self.get_return_pattern(keyword)

            for path in self.search_path:
                file_name = os.path.join(path, header)
                try:
                    with open(file_name, 'rb') as f:
                        for i, l in enumerate(f):
                            result = pattern.findall(l)
                            if result:
                                # Don't add comment lines
                                if not re.findall(func_pattern, l):
                                    if ';' not in l and '#define' not in l:
                                        continue
                                if return_value_pattern.findall(l):
                                    continue
                                if return_pattern.findall(l):
                                    continue
                                result = '{0};{1};{2}'.format(file_name,
                                                              i + 1,
                                                              l)
                                self.result_list.append(result)
                            header_result = self.header_pattern.findall(l)
                            if header_result:
                                for next_header in header_result:
                                    next_headers.append(next_header)
                except IOError:
                    continue

        # Record searched headers.
        self.searched_header_list += headers

        if len(next_headers):
            next_headers = \
                list(set([h for h in next_headers
                          if h not in self.searched_header_list]))
            self.search(next_headers, pattern, keyword)
