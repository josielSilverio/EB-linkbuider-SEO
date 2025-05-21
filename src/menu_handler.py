from typing import Optional, Tuple, Dict
import logging
from src.config import config

logger = logging.getLogger('seo_linkbuilder.menu')

class MenuHandler:
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler

    def apresentar_menu_planilha(self, ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
        """Apresenta menu para seleção da planilha e pasta do Drive"""
        try:
            # Mostra última planilha e pasta utilizadas
            if ultima_selecao:
                print("\nÚltima configuração utilizada:")
                print(f"Planilha ID: {ultima_selecao.get('spreadsheet_id', 'Não disponível')}")
                print(f"Aba: {ultima_selecao.get('sheet_name', 'Não disponível')}")
                print(f"Pasta Drive ID: {ultima_selecao.get('drive_folder_id', 'Não disponível')}")
                usar_ultima = input("\nDeseja usar a última configuração? (S/N ou 0 para cancelar): ").upper()
                if usar_ultima == '0':
                    return None
                if usar_ultima == 'S':
                    return (
                        ultima_selecao.get('spreadsheet_id'),
                        ultima_selecao.get('sheet_name', 'Sheet1'),
                        ultima_selecao.get('drive_folder_id')
                    )

            # Lista todas as planilhas disponíveis
            planilhas = self.sheets_handler.obter_planilhas_disponiveis()
            if not planilhas:
                print("Nenhuma planilha encontrada.")
                return None

            return self._menu_selecao_planilha(planilhas, ultima_selecao)

        except Exception as e:
            logger.error(f"Erro ao apresentar menu de planilhas: {e}")
            return None

    def _menu_selecao_planilha(self, planilhas: list, ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
        """Menu de seleção de planilha"""
        print("\nPlanilhas disponíveis:")
        for i, planilha in enumerate(planilhas, 1):
            print(f"{i}. {planilha['name']}")
        print(f"{len(planilhas)+1}. Adicionar planilha manualmente pelo ID")
        print("0. Cancelar")

        while True:
            try:
                escolha = int(input("\nEscolha o número da planilha (ou 0 para sair): "))
                if escolha == 0:
                    return None
                if 1 <= escolha <= len(planilhas):
                    return self._processar_planilha_existente(planilhas[escolha - 1], ultima_selecao)
                elif escolha == len(planilhas) + 1:
                    return self._processar_planilha_manual(ultima_selecao)
                print("Opção inválida. Tente novamente.")
            except ValueError:
                print("Por favor, digite um número válido.")

    def _processar_planilha_existente(self, planilha: Dict, ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
        """Processa seleção de planilha existente"""
        planilha_id = planilha['id']
        planilha_nome = planilha['name']
        
        abas = self.sheets_handler.obter_abas_disponiveis(planilha_id)
        if not abas:
            print("Nenhuma aba encontrada nesta planilha.")
            return None
            
        return self._menu_selecao_aba(abas, planilha_nome, planilha_id, ultima_selecao)

    def _menu_selecao_aba(self, abas: list, planilha_nome: str, planilha_id: str, 
                         ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
        """Menu de seleção de aba"""
        print(f"\nAbas disponíveis na planilha '{planilha_nome}':")
        for j, aba in enumerate(abas, 1):
            print(f"{j}. {aba['titulo']}")
        print("0. Cancelar")
        
        while True:
            try:
                escolha_aba = int(input("\nEscolha o número da aba (ou 0 para cancelar): "))
                if escolha_aba == 0:
                    return None
                if 1 <= escolha_aba <= len(abas):
                    aba_nome = abas[escolha_aba - 1]['titulo']
                    drive_folder_id = self._obter_drive_folder_id(ultima_selecao)
                    if not drive_folder_id:
                        return None
                    print(f"\nPlanilha selecionada: {planilha_nome} ({planilha_id}) | Aba: {aba_nome}")
                    return planilha_id, aba_nome, drive_folder_id
                print("Opção de aba inválida. Tente novamente.")
            except ValueError:
                print("Por favor, digite um número válido.")

    def _processar_planilha_manual(self, ultima_selecao: Dict) -> Optional[Tuple[str, str, str]]:
        """Processa entrada manual de planilha"""
        planilha_id = input("\nDigite o ID da planilha do Google Sheets (ou 0 para cancelar): ").strip()
        if planilha_id == '0':
            return None
        if not planilha_id:
            print("ID da planilha é obrigatório.")
            return None
            
        sheet_name = input("Digite o nome da aba (sheet) a ser utilizada (ou 0 para cancelar): ").strip()
        if sheet_name == '0':
            return None
        if not sheet_name:
            print("Nome da aba é obrigatório.")
            return None
            
        drive_folder_id = self._obter_drive_folder_id(ultima_selecao)
        if not drive_folder_id:
            return None
            
        print(f"\nPlanilha selecionada: {planilha_id} | Aba: {sheet_name}")
        return planilha_id, sheet_name, drive_folder_id

    def _obter_drive_folder_id(self, ultima_selecao: Dict) -> Optional[str]:
        """Obtém ID da pasta do Drive"""
        if ultima_selecao and ultima_selecao.get('drive_folder_id'):
            print(f"\nÚltima pasta do Drive utilizada: {ultima_selecao['drive_folder_id']}")
            drive_folder_id_input = input("Pressione Enter para usar a última pasta ou digite um novo ID: ").strip()
            if drive_folder_id_input:
                return drive_folder_id_input
            return ultima_selecao['drive_folder_id']
            
        drive_folder_id = input("Digite o ID da pasta do Drive para salvar os documentos (ou 0 para cancelar): ").strip()
        if drive_folder_id == '0':
            return None
        if not drive_folder_id:
            print("ID da pasta do Drive é obrigatório.")
            return None
        return drive_folder_id

    @staticmethod
    def apresentar_menu_processamento() -> str:
        """Apresenta menu para seleção do tipo de processamento"""
        print("\nOpções de processamento:")
        print("1. Gerar apenas títulos")
        print("2. Gerar apenas conteúdos")
        print("3. Gerar títulos e conteúdos")
        print("0. Sair/Cancelar")

        while True:
            escolha = input("\nEscolha uma opção: ")
            if escolha in ["0", "1", "2", "3"]:
                return escolha
            print("Opção inválida. Tente novamente.")

    @staticmethod
    def apresentar_menu_quantidade() -> Optional[int]:
        """Menu para escolher quantidade de linhas a processar"""
        print("\nQuantos itens deseja processar?")
        print("1. Gerar tudo (todos os não preenchidos)")
        print("2. Gerar número específico")
        print("3. Cancelar")
        
        while True:
            escolha = input("\nEscolha uma opção: ").strip()
            if escolha == '1':
                return None  # None = processar tudo
            elif escolha == '2':
                try:
                    qtd = int(input("Digite o número de itens a processar: ").strip())
                    if qtd > 0:
                        return qtd
                    print("Digite um número maior que zero.")
                except ValueError:
                    print("Valor inválido. Tente novamente.")
            elif escolha == '3':
                return 'cancelar'
            print("Opção inválida. Tente novamente.") 