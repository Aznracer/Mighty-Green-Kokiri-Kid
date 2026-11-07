import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'dm/host/hle_thread.c'
s = open(p).read()
if 'static inline void g_unlock(void) {' not in s: sys.exit('the wake patch is not in: nothing changed')
s = s.replace('pthread_mutex_unlock(&G);', 'g_unlock();')
inner = '    t_nwdef = 0;\n    g_unlock();\n'
if s.count(inner) != 1: sys.exit('g_unlock body not found once: nothing changed')
s = s.replace(inner, '    t_nwdef = 0;\n    pthread_mutex_unlock(&G);\n')
if s.count('pthread_mutex_unlock(&G);') != 1: sys.exit('unexpected unlocks left: nothing changed')
open(p, 'w').write(s); print('patched', p, ': every unlock of G goes through g_unlock')
