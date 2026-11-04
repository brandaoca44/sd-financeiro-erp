export default {
  '/api/**': {
    target: `http://127.0.0.1:${Number(process.env.SDF_API_PORT || 8000)}`,
    changeOrigin: false,
    configure(proxy) {
      // Não imprimir URL, headers ou detalhes de conexão em erros do proxy local.
      proxy.removeAllListeners('error');
      proxy.on('error', (_error, _request, response) => {
        if (response && typeof response.writeHead === 'function' && !response.headersSent) {
          response.writeHead(503, {'Content-Type':'application/json','Cache-Control':'no-store'});
          response.end('{"detail":"Serviço temporariamente indisponível."}');
        } else if (response && typeof response.destroy === 'function') {
          response.destroy();
        }
      });
    }
  }
};
