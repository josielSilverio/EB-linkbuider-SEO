import sqlite3
import pandas as pd
from src.db_handler import DBHandler

def mostrar_estatisticas_db():
    """Mostra estatísticas do banco de dados de aprendizado"""
    db = DBHandler()
    
    # Conecta ao banco
    with sqlite3.connect(db.db_path) as conn:
        # Total de títulos
        total_titulos = pd.read_sql("SELECT COUNT(*) as total FROM titles", conn).iloc[0]['total']
        print(f"\nTotal de títulos armazenados: {total_titulos}")
        
        # Média de performance e feedback
        metricas = pd.read_sql("""
            SELECT 
                AVG(performance_score) as avg_performance,
                AVG(feedback_score) as avg_feedback,
                COUNT(CASE WHEN feedback_score > 0 THEN 1 END) as total_feedback
            FROM titles
        """, conn).iloc[0]
        
        print(f"Média de performance: {metricas['avg_performance']:.2f}")
        print(f"Média de feedback: {metricas['avg_feedback']:.2f}")
        print(f"Total de títulos com feedback: {metricas['total_feedback']}")
        
        # Top temas
        print("\nDistribuição por tema principal:")
        temas = pd.read_sql("""
            SELECT 
                main_theme,
                COUNT(*) as total,
                AVG(performance_score) as avg_performance,
                AVG(feedback_score) as avg_feedback
            FROM titles
            GROUP BY main_theme
            ORDER BY total DESC
        """, conn)
        
        for _, tema in temas.iterrows():
            print(f"\n{tema['main_theme']}:")
            print(f"  Total: {tema['total']}")
            print(f"  Performance média: {tema['avg_performance']:.2f}")
            print(f"  Feedback médio: {tema['avg_feedback']:.2f}")
        
        # Estruturas bem-sucedidas
        print("\nPadrões de estrutura bem-sucedidos:")
        estruturas = pd.read_sql("""
            SELECT 
                structure_pattern,
                theme,
                success_count,
                last_used
            FROM successful_structures
            ORDER BY success_count DESC
            LIMIT 5
        """, conn)
        
        for _, estrutura in estruturas.iterrows():
            print(f"\nPadrão: {estrutura['structure_pattern']}")
            print(f"Tema: {estrutura['theme']}")
            print(f"Sucesso: {estrutura['success_count']}")
            print(f"Último uso: {estrutura['last_used']}")

if __name__ == "__main__":
    mostrar_estatisticas_db() 