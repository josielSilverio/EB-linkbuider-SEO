import asyncio
from src.gemini_handler import GeminiHandler
from src.menu_handler import MenuHandler

async def main():
    # Inicializa os handlers
    gemini = GeminiHandler()
    menu = MenuHandler()
    
    # Exemplo de palavra-âncora e prompt
    palavra_ancora = "apostas online"
    prompt = gemini.carregar_prompt_template(tipo='titulos')
    
    # 1. Gerar título
    print("\n1. Gerando título...")
    titulo = await gemini.gerar_titulo(palavra_ancora, prompt)
    print(f"Título gerado: {titulo}")
    
    # 2. Simular feedback do usuário
    print("\n2. Avaliando título...")
    feedback = menu.avaliar_titulo(titulo)
    
    # 3. Atualizar o sistema com o feedback
    print("\n3. Atualizando sistema de aprendizado...")
    gemini.atualizar_desempenho_titulo(
        titulo=titulo,
        performance_score=0.8,  # Exemplo: 80% de cliques
        feedback_score=feedback  # Feedback do usuário (0-1)
    )
    
    # 4. Verificar estatísticas do tema
    print("\n4. Verificando estatísticas...")
    tema = gemini._extrair_tema_principal(titulo)
    stats = gemini.db.get_theme_statistics(tema)
    print(f"\nEstatísticas para o tema '{tema}':")
    print(f"- Total de títulos: {stats['total_titles']}")
    print(f"- Média de performance: {stats['avg_performance']:.2f}")
    print(f"- Média de feedback: {stats['avg_feedback']:.2f}")
    print(f"- Títulos aprovados: {stats['approved_count']}")
    
    # 5. Buscar títulos similares bem-sucedidos
    print("\n5. Buscando títulos similares bem-sucedidos...")
    similares = gemini.db.get_similar_successful_titles(
        anchor_word=palavra_ancora,
        theme=tema
    )
    if similares:
        print("\nTítulos similares bem-sucedidos:")
        for titulo in similares:
            print(f"- {titulo['title']}")
            print(f"  Performance: {titulo['performance']:.2f}")
            print(f"  Feedback: {titulo['feedback']:.2f}")
    else:
        print("Ainda não há títulos similares bem-sucedidos.")
    
    # 6. Verificar padrões de estrutura bem-sucedidos
    print("\n6. Verificando padrões de estrutura bem-sucedidos...")
    padroes = gemini.db.get_successful_patterns(tema)
    if padroes:
        print("\nPadrões de estrutura bem-sucedidos:")
        for padrao in padroes:
            print(f"- Padrão: {padrao['pattern']}")
            print(f"  Contagem de sucesso: {padrao['success_count']}")
    else:
        print("Ainda não há padrões de estrutura bem-sucedidos.")

if __name__ == "__main__":
    asyncio.run(main()) 