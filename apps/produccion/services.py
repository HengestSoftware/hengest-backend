import math
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Sum


def format_num_es(val, decimals=1):
    """Formatea un número con coma decimal (estilo Colombia / español)."""
    if val is None:
        return "0,0"
    formatted = f"{val:.{decimals}f}"
    return formatted.replace('.', ',')


def calcular_cubetas(aaa, aa, a, b, c):
    """
    Calcula cubetas (paquetes de 30 unidades) y sueltos para cada categoría y totales.
    """
    categorias = {'aaa': aaa, 'aa': aa, 'a': a, 'b': b, 'c': c}
    resultado_cubetas = {}
    total_cubetas = 0
    total_sueltos = 0
    total_huevos = 0

    for cat, unidades in categorias.items():
        unidades = unidades or 0
        total_huevos += unidades
        cub = unidades // 30
        sue = unidades % 30
        resultado_cubetas[cat] = {
            'cubetas': cub,
            'sueltos': sue
        }
        total_cubetas += cub
        total_sueltos += sue

    return {
        'total_huevos': total_huevos,
        'cubetas': resultado_cubetas,
        'total_cubetas': total_cubetas,
        'total_sueltos': total_sueltos,
    }


def calcular_aves_vivas_a_fecha(lote, fecha, excluir_registro_id=None):
    """
    Devuelve las aves vivas al INICIO del día y al FINAL del día para una fecha dada.
    Aves vivas final = aves_iniciales - sum(mortalidad + descarte) hasta esa fecha inclusive.
    Aves vivas inicio = aves_iniciales - sum(mortalidad + descarte) antes de esa fecha.
    """
    from apps.produccion.models import RegistroDiario

    # Aves antes de la fecha (inicio del día)
    qs_antes = RegistroDiario.objects.filter(lote=lote, fecha__lt=fecha)
    if excluir_registro_id:
        qs_antes = qs_antes.exclude(id=excluir_registro_id)

    totales_antes = qs_antes.aggregate(
        tot_mortalidad=Sum('mortalidad'),
        tot_descarte=Sum('descarte')
    )
    mortalidad_antes = totales_antes['tot_mortalidad'] or 0
    descarte_antes = totales_antes['tot_descarte'] or 0
    aves_vivas_inicio = max(0, lote.aves_iniciales - mortalidad_antes - descarte_antes)

    # Aves hasta la fecha inclusive (final del día)
    qs_hasta = RegistroDiario.objects.filter(lote=lote, fecha__lte=fecha)
    if excluir_registro_id:
        qs_hasta = qs_hasta.exclude(id=excluir_registro_id)

    totales_hasta = qs_hasta.aggregate(
        tot_mortalidad=Sum('mortalidad'),
        tot_descarte=Sum('descarte')
    )
    mortalidad_hasta = totales_hasta['tot_mortalidad'] or 0
    descarte_hasta = totales_hasta['tot_descarte'] or 0
    aves_vivas_final = max(0, lote.aves_iniciales - mortalidad_hasta - descarte_hasta)

    return aves_vivas_inicio, aves_vivas_final


def calcular_semana_vida(lote, fecha):
    """
    Semana de vida = edad_inicial_semanas + floor((fecha - fecha_ingreso).days / 7)
    """
    dias = (fecha - lote.fecha_ingreso).days
    return lote.edad_inicial_semanas + math.floor(dias / 7)


def calcular_kpis_registro(lote, fecha, alimento_kg, total_huevos, aves_vivas_inicio):
    """
    Calcula postura %, consumo g/ave, conversión alimenticia y conversión kg/kg.
    """
    alimento_kg = float(alimento_kg or 0.0)

    # Postura %
    if aves_vivas_inicio > 0:
        postura_pct = round((total_huevos / aves_vivas_inicio) * 100, 1)
        consumo_g_ave = round((alimento_kg * 1000) / aves_vivas_inicio, 1)
    else:
        postura_pct = 0.0
        consumo_g_ave = 0.0

    # Conversión alimenticia (kg alimento / docena de huevos)
    if total_huevos > 0:
        docenas = total_huevos / 12.0
        conversion_alimenticia = round(alimento_kg / docenas, 2)
    else:
        conversion_alimenticia = None

    # Conversión kg alimento / kg de huevo (si el lote define peso_promedio_huevo_g)
    conversion_kg_kg = None
    if lote.peso_promedio_huevo_g and total_huevos > 0:
        peso_huevo_kg = float(lote.peso_promedio_huevo_g) / 1000.0
        kilos_huevo = total_huevos * peso_huevo_kg
        if kilos_huevo > 0:
            conversion_kg_kg = round(alimento_kg / kilos_huevo, 2)

    return {
        'postura_pct': postura_pct,
        'consumo_g_ave': consumo_g_ave,
        'conversion_alimenticia': conversion_alimenticia,
        'conversion_kg_kg': conversion_kg_kg,
    }


def evaluar_alertas_registro(registro):
    """
    Evalúa y recrea dentro de una transacción las alertas del lote para la fecha del registro.
    Reglas de postura, mortalidad y consumo frente al estándar de la semana.
    """
    from apps.produccion.models import Alerta, RegistroDiario
    from apps.granjas.models import EstandarSemanal

    lote = registro.lote
    granja = lote.granja
    fecha = registro.fecha

    with transaction.atomic():
        # Borrar alertas previas de ese lote y fecha
        Alerta.objects.filter(lote=lote, fecha=fecha).delete()

        semana_vida = calcular_semana_vida(lote, fecha)
        estandar = EstandarSemanal.objects.filter(lote=lote, semana=semana_vida).first()

        # Si no hay estándar para esa semana: sin_estandar = True y NO se generan alertas
        if not estandar:
            return []

        cubetas_info = calcular_cubetas(
            registro.aaa, registro.aa, registro.a, registro.b, registro.c
        )
        total_huevos = cubetas_info['total_huevos']

        aves_vivas_inicio, _ = calcular_aves_vivas_a_fecha(lote, fecha, excluir_registro_id=registro.id)
        # Si el registro ya existe o es nuevo, aves_vivas_inicio no incluye la mortalidad de hoy
        if aves_vivas_inicio <= 0:
            return []

        kpis = calcular_kpis_registro(
            lote, fecha, registro.alimento_kg, total_huevos, aves_vivas_inicio
        )
        postura_pct = kpis['postura_pct']
        consumo_g_ave = kpis['consumo_g_ave']

        alertas_a_crear = []

        # 1. ALERTAS DE POSTURA
        esperada = estandar.postura_esperada_pct
        umbral_critico = granja.umbral_postura_critico_pts
        umbral_adv = granja.umbral_postura_pts

        diff = round(postura_pct - esperada, 1)
        diff_signo = f"+{format_num_es(diff)}" if diff > 0 else format_num_es(diff)

        if postura_pct < (esperada - umbral_critico):
            msg = (
                f"La postura fue {format_num_es(postura_pct)} % y lo esperado era "
                f"{format_num_es(esperada)} % ({diff_signo} pts)."
            )
            alertas_a_crear.append(Alerta(
                granja=granja,
                lote=lote,
                fecha=fecha,
                tipo='POSTURA',
                severidad='CRITICA',
                mensaje=msg,
                valor_observado=postura_pct,
                valor_esperado=esperada
            ))
        elif postura_pct < (esperada - umbral_adv):
            msg = (
                f"La postura fue {format_num_es(postura_pct)} % y lo esperado era "
                f"{format_num_es(esperada)} % ({diff_signo} pts)."
            )
            alertas_a_crear.append(Alerta(
                granja=granja,
                lote=lote,
                fecha=fecha,
                tipo='POSTURA',
                severidad='ADVERTENCIA',
                mensaje=msg,
                valor_observado=postura_pct,
                valor_esperado=esperada
            ))

        # Caída súbita frente al promedio de los 3 días previos
        fecha_inicio_3d = fecha - timedelta(days=3)
        registros_previos = RegistroDiario.objects.filter(
            lote=lote,
            fecha__gte=fecha_inicio_3d,
            fecha__lt=fecha
        ).exclude(id=registro.id)

        if registros_previos.exists():
            posturas_previas = []
            for rp in registros_previos:
                c_prev = calcular_cubetas(rp.aaa, rp.aa, rp.a, rp.b, rp.c)['total_huevos']
                av_prev, _ = calcular_aves_vivas_a_fecha(lote, rp.fecha, excluir_registro_id=rp.id)
                if av_prev > 0:
                    posturas_previas.append((c_prev / av_prev) * 100)

            if posturas_previas:
                promedio_3d = sum(posturas_previas) / len(posturas_previas)
                if (promedio_3d - postura_pct) > umbral_adv:
                    # Si no hay ya alerta crítica por postura o si queremos registrar la caída súbita
                    msg_caida = (
                        f"Caída súbita de postura: {format_num_es(postura_pct)} % frente al promedio "
                        f"de los 3 días previos ({format_num_es(promedio_3d)} %)."
                    )
                    # Solo la añadimos si no hay ya una advertencia idéntica
                    ya_existe_adv = any(a.tipo == 'POSTURA' and a.severidad == 'ADVERTENCIA' for a in alertas_a_crear)
                    if not ya_existe_adv and not any(a.tipo == 'POSTURA' and a.severidad == 'CRITICA' for a in alertas_a_crear):
                        alertas_a_crear.append(Alerta(
                            granja=granja,
                            lote=lote,
                            fecha=fecha,
                            tipo='POSTURA',
                            severidad='ADVERTENCIA',
                            mensaje=msg_caida,
                            valor_observado=postura_pct,
                            valor_esperado=round(promedio_3d, 1)
                        ))

        # 2. ALERTAS DE MORTALIDAD
        # (a) Pico diario
        pct_mortalidad_dia = (registro.mortalidad / aves_vivas_inicio) * 100
        umbral_mort_dia = granja.umbral_mortalidad_diaria_pct

        if pct_mortalidad_dia > umbral_mort_dia:
            es_critica = pct_mortalidad_dia >= (umbral_mort_dia * 2)
            severidad = 'CRITICA' if es_critica else 'ADVERTENCIA'
            msg_mort = (
                f"Mortalidad diaria de {format_num_es(pct_mortalidad_dia, 2)} % supera el umbral "
                f"permitido de {format_num_es(umbral_mort_dia, 2)} % ({registro.mortalidad} aves)."
            )
            alertas_a_crear.append(Alerta(
                granja=granja,
                lote=lote,
                fecha=fecha,
                tipo='MORTALIDAD',
                severidad=severidad,
                mensaje=msg_mort,
                valor_observado=round(pct_mortalidad_dia, 2),
                valor_esperado=umbral_mort_dia
            ))

        # (b) Acumulado 7 días móviles hasta la fecha
        fecha_inicio_7d = fecha - timedelta(days=6)
        registros_7d = list(RegistroDiario.objects.filter(
            lote=lote,
            fecha__gte=fecha_inicio_7d,
            fecha__lte=fecha
        ).exclude(id=registro.id))
        # Incluir el registro actual
        total_mortalidad_7d = sum(r.mortalidad for r in registros_7d) + registro.mortalidad

        # Aves vivas al inicio de esa ventana (7 días atrás)
        aves_vivas_inicio_7d, _ = calcular_aves_vivas_a_fecha(lote, fecha_inicio_7d, excluir_registro_id=registro.id)
        if aves_vivas_inicio_7d > 0:
            pct_mort_7d = (total_mortalidad_7d / aves_vivas_inicio_7d) * 100
            max_semanal = estandar.mortalidad_max_semanal_pct
            if pct_mort_7d > max_semanal:
                es_critica = pct_mort_7d >= (max_semanal * 2)
                severidad = 'CRITICA' if es_critica else 'ADVERTENCIA'
                msg_7d = (
                    f"Mortalidad acumulada de 7 días ({format_num_es(pct_mort_7d, 2)} %) supera "
                    f"el estándar semanal de {format_num_es(max_semanal, 2)} %."
                )
                alertas_a_crear.append(Alerta(
                    granja=granja,
                    lote=lote,
                    fecha=fecha,
                    tipo='MORTALIDAD',
                    severidad=severidad,
                    mensaje=msg_7d,
                    valor_observado=round(pct_mort_7d, 2),
                    valor_esperado=max_semanal
                ))

        # 3. ALERTAS DE CONSUMO
        consumo_esperado = estandar.consumo_g_ave_dia
        if consumo_esperado > 0:
            desviacion_abs = abs(consumo_g_ave - consumo_esperado)
            desviacion_pct = (desviacion_abs / consumo_esperado) * 100

            if desviacion_pct > granja.umbral_consumo_critico_pct:
                msg_cons = (
                    f"Consumo de alimento ({format_num_es(consumo_g_ave)} g/ave) se desvió un "
                    f"{format_num_es(desviacion_pct)} % del estándar ({format_num_es(consumo_esperado)} g/ave)."
                )
                alertas_a_crear.append(Alerta(
                    granja=granja,
                    lote=lote,
                    fecha=fecha,
                    tipo='CONSUMO',
                    severidad='CRITICA',
                    mensaje=msg_cons,
                    valor_observado=consumo_g_ave,
                    valor_esperado=consumo_esperado
                ))
            elif desviacion_pct > granja.umbral_consumo_pct:
                msg_cons = (
                    f"Consumo de alimento ({format_num_es(consumo_g_ave)} g/ave) se desvió un "
                    f"{format_num_es(desviacion_pct)} % del estándar ({format_num_es(consumo_esperado)} g/ave)."
                )
                alertas_a_crear.append(Alerta(
                    granja=granja,
                    lote=lote,
                    fecha=fecha,
                    tipo='CONSUMO',
                    severidad='ADVERTENCIA',
                    mensaje=msg_cons,
                    valor_observado=consumo_g_ave,
                    valor_esperado=consumo_esperado
                ))

        # Guardar todas las alertas
        if alertas_a_crear:
            Alerta.objects.bulk_create(alertas_a_crear)

        return list(Alerta.objects.filter(lote=lote, fecha=fecha))
