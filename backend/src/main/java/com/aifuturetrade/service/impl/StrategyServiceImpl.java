package com.aifuturetrade.service.impl;

import com.aifuturetrade.dao.entity.StrategyDO;
import com.aifuturetrade.dao.mapper.StrategyMapper;
import com.aifuturetrade.service.AiProviderService;
import com.aifuturetrade.service.ProviderService;
import com.aifuturetrade.service.SettingsService;
import com.aifuturetrade.service.StrategyService;
import com.aifuturetrade.service.StrategyCodeTesterService;
import com.aifuturetrade.service.dto.ProviderDTO;
import com.aifuturetrade.service.dto.StrategyDTO;
import com.aifuturetrade.common.util.PageResult;
import com.aifuturetrade.common.util.PageRequest;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import lombok.extern.slf4j.Slf4j;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 业务逻辑实现类：策略
 * 实现策略的业务逻辑
 */
@Slf4j
@Service
public class StrategyServiceImpl implements StrategyService {

    @Autowired
    private StrategyMapper strategyMapper;
    
    @Autowired
    private StrategyCodeTesterService strategyCodeTesterService;

    @Autowired
    private AiProviderService aiProviderService;

    @Autowired
    private SettingsService settingsService;

    @Autowired
    private ProviderService providerService;

    @Override
    public List<StrategyDTO> getAllStrategies() {
        List<StrategyDO> strategyDOList = strategyMapper.selectAllStrategies();
        return strategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public StrategyDTO getStrategyById(String id) {
        StrategyDO strategyDO = strategyMapper.selectStrategyById(id);
        return strategyDO != null ? convertToDTO(strategyDO) : null;
    }

    @Override
    public List<StrategyDTO> getStrategiesByCondition(String name, String type) {
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(name)) {
            queryWrapper.like(StrategyDO::getName, name);
        }
        if (StringUtils.hasText(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        List<StrategyDO> strategyDOList = strategyMapper.selectList(queryWrapper);
        return strategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public List<StrategyDTO> getStrategiesByKeyword(String keyword, String type) {
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(keyword)) {
            queryWrapper.and(wrapper -> wrapper
                    .like(StrategyDO::getName, keyword)
                    .or()
                    .like(StrategyDO::getStrategyContext, keyword)
            );
        }
        if (StringUtils.hasText(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        List<StrategyDO> strategyDOList = strategyMapper.selectList(queryWrapper);
        return strategyDOList.stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    public PageResult<StrategyDTO> getStrategiesByPage(PageRequest pageRequest, String name, String type) {
        Page<StrategyDO> page = new Page<>(pageRequest.getPageNum(), pageRequest.getPageSize());
        
        LambdaQueryWrapper<StrategyDO> queryWrapper = new LambdaQueryWrapper<>();
        // 过滤掉 null、"undefined" 字符串和空字符串
        if (StringUtils.hasText(name) && !"undefined".equalsIgnoreCase(name)) {
            queryWrapper.like(StrategyDO::getName, name);
        }
        if (StringUtils.hasText(type) && !"undefined".equalsIgnoreCase(type)) {
            queryWrapper.eq(StrategyDO::getType, type);
        }
        queryWrapper.orderByDesc(StrategyDO::getCreatedAt);
        
        Page<StrategyDO> strategyDOPage = strategyMapper.selectPage(page, queryWrapper);
        
        List<StrategyDTO> strategyDTOList = strategyDOPage.getRecords().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
        
        return PageResult.build(strategyDTOList, strategyDOPage.getTotal(), pageRequest.getPageNum(), pageRequest.getPageSize());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StrategyDTO addStrategy(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = convertToDO(strategyDTO);
        if (strategyDO.getId() == null || strategyDO.getId().isEmpty()) {
            strategyDO.setId(UUID.randomUUID().toString());
        }

        // 与「获取代码」一致：有 strategy_context 且无 strategy_code 时，使用系统设置中的策略 API 提供方与模型生成并测试
        Optional<Map<String, Object>> aiGenerationMeta = maybeGenerateStrategyCodeOnCreate(strategyDTO, strategyDO);

        // 如果提供了策略代码，进行测试验证
        if (strategyDO.getStrategyCode() != null && !strategyDO.getStrategyCode().trim().isEmpty()) {
            String strategyType = strategyDO.getType();
            String strategyName = strategyDO.getName() != null ? strategyDO.getName() : "新策略";
            
            if (strategyType == null || strategyType.trim().isEmpty()) {
                throw new IllegalArgumentException("策略类型不能为空，无法验证策略代码");
            }
            
            try {
                if ("look".equalsIgnoreCase(strategyType)) {
                    String sym = strategyDTO.getValidateSymbol();
                    if (sym == null || sym.trim().isEmpty()) {
                        throw new IllegalArgumentException("盯盘策略必须提供 validate_symbol 用于行情验证");
                    }
                    strategyCodeTesterService.validateLookStrategyCode(
                            strategyDO.getStrategyCode(),
                            strategyName,
                            sym.trim()
                    );
                } else {
                    strategyCodeTesterService.validateStrategyCode(
                        strategyDO.getStrategyCode(), 
                        strategyType, 
                        strategyName
                    );
                }
                log.info("策略代码验证通过: {}", strategyName);
            } catch (Exception e) {
                log.error("策略代码验证失败: {}, 错误: {}", strategyName, e.getMessage());
                throw new RuntimeException("策略代码验证失败，无法保存: " + e.getMessage(), e);
            }
        }
        
        strategyDO.setCreatedAt(LocalDateTime.now());
        strategyDO.setUpdatedAt(LocalDateTime.now());
        strategyMapper.insert(strategyDO);
        StrategyDTO out = convertToDTO(strategyDO);
        aiGenerationMeta.ifPresent(meta -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> testResult = (Map<String, Object>) meta.get("testResult");
            out.setGenerationTestResult(testResult);
            out.setGenerationTestPassed(Boolean.TRUE.equals(meta.get("testPassed")));
        });
        return out;
    }

    /**
     * 创建时若有 strategy_context 且无 strategy_code，则从系统设置读取策略 API 提供方与模型，走完整生成与测试。
     *
     * @return 若执行了 AI 生成且测试通过，携带 testResult / testPassed，否则 empty
     */
    private Optional<Map<String, Object>> maybeGenerateStrategyCodeOnCreate(StrategyDTO strategyDTO, StrategyDO strategyDO) {
        if (strategyDO.getStrategyCode() != null && !strategyDO.getStrategyCode().trim().isEmpty()) {
            return Optional.empty();
        }
        if (!StringUtils.hasText(strategyDTO.getStrategyContext())) {
            return Optional.empty();
        }
        String[] pm = resolveStrategyProviderAndModel();
        String pid = pm[0];
        String model = pm[1];
        String strategyType = strategyDO.getType();
        if (strategyType == null || strategyType.trim().isEmpty()) {
            throw new IllegalArgumentException("策略类型不能为空，无法生成策略代码");
        }
        String typeNorm = strategyType.trim().toLowerCase();
        if (!"buy".equals(typeNorm) && !"sell".equals(typeNorm) && !"look".equals(typeNorm)) {
            throw new IllegalArgumentException("strategy type must be buy, sell, or look");
        }
        String validateSym = null;
        if ("look".equals(typeNorm)) {
            validateSym = strategyDTO.getValidateSymbol();
            if (!StringUtils.hasText(validateSym)) {
                throw new IllegalArgumentException("盯盘策略用 AI 生成代码时必须提供 validate_symbol（与「获取代码」一致，用于合约校验与测试）");
            }
            validateSym = validateSym.trim();
        }
        String context = strategyDTO.getStrategyContext().trim();
        String generatedCode = aiProviderService.generateStrategyCode(pid, model, context, typeNorm);

        String testName = strategyDTO.getName() != null && StringUtils.hasText(strategyDTO.getName().trim())
                ? strategyDTO.getName().trim()
                : ("look".equals(typeNorm) ? "新盯盘策略" : "新" + ("buy".equals(typeNorm) ? "买入" : "卖出") + "策略");

        Map<String, Object> testResult;
        if ("look".equals(typeNorm)) {
            testResult = strategyCodeTesterService.testLookStrategyCode(generatedCode, testName, validateSym);
        } else {
            testResult = strategyCodeTesterService.testStrategyCode(generatedCode, typeNorm, testName);
        }
        if (!Boolean.TRUE.equals(testResult.get("passed"))) {
            @SuppressWarnings("unchecked")
            List<String> errs = (List<String>) testResult.get("errors");
            String detail = errs != null && !errs.isEmpty() ? String.join("; ", errs) : String.valueOf(testResult.get("message") != null ? testResult.get("message") : testResult);
            throw new RuntimeException("AI 生成的策略代码未通过测试，无法保存: " + detail);
        }
        strategyDO.setStrategyCode(generatedCode);
        Map<String, Object> meta = new HashMap<>();
        meta.put("testPassed", true);
        meta.put("testResult", testResult);
        return Optional.of(meta);
    }

    /**
     * 与前端「设置策略API提供方」一致：settings.strategy_provider / strategy_model；模型未配置时尝试使用提供方 models 字段首项。
     */
    private String[] resolveStrategyProviderAndModel() {
        Map<String, Object> settings = settingsService.getSettings();
        Object p = settings.get("strategy_provider");
        Object m = settings.get("strategy_model");
        String providerId = p != null ? p.toString().trim() : null;
        String modelName = m != null ? m.toString().trim() : null;
        if (!StringUtils.hasText(providerId)) {
            throw new IllegalArgumentException("请先在系统设置中配置策略API提供方（与「获取代码」使用的配置相同）");
        }
        if (!StringUtils.hasText(modelName)) {
            ProviderDTO prov = providerService.getProviderById(providerId);
            if (prov != null && StringUtils.hasText(prov.getModels())) {
                for (String part : prov.getModels().split(",")) {
                    String mm = part.trim();
                    if (StringUtils.hasText(mm)) {
                        modelName = mm;
                        break;
                    }
                }
            }
        }
        if (!StringUtils.hasText(modelName)) {
            throw new IllegalArgumentException("请先在系统设置中选择策略所用模型，或在API提供方中配置可用模型列表");
        }
        return new String[]{providerId, modelName};
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StrategyDTO updateStrategy(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = convertToDO(strategyDTO);
        
        // 如果更新了策略代码，进行测试验证
        if (strategyDO.getStrategyCode() != null && !strategyDO.getStrategyCode().trim().isEmpty()) {
            String strategyType = strategyDO.getType();
            String strategyName = strategyDO.getName() != null ? strategyDO.getName() : "策略";
            
            // 如果类型为空，尝试从数据库获取
            if (strategyType == null || strategyType.trim().isEmpty()) {
                StrategyDO existingStrategy = strategyMapper.selectById(strategyDO.getId());
                if (existingStrategy != null) {
                    strategyType = existingStrategy.getType();
                }
            }
            
            if (strategyType == null || strategyType.trim().isEmpty()) {
                throw new IllegalArgumentException("策略类型不能为空，无法验证策略代码");
            }
            
            try {
                if ("look".equalsIgnoreCase(strategyType)) {
                    String sym = strategyDTO.getValidateSymbol();
                    if (sym == null || sym.trim().isEmpty()) {
                        throw new IllegalArgumentException("盯盘策略必须提供 validate_symbol 用于行情验证");
                    }
                    strategyCodeTesterService.validateLookStrategyCode(
                            strategyDO.getStrategyCode(),
                            strategyName,
                            sym.trim()
                    );
                } else {
                    strategyCodeTesterService.validateStrategyCode(
                        strategyDO.getStrategyCode(), 
                        strategyType, 
                        strategyName
                    );
                }
                log.info("策略代码验证通过: {}", strategyName);
            } catch (Exception e) {
                log.error("策略代码验证失败: {}, 错误: {}", strategyName, e.getMessage());
                throw new RuntimeException("策略代码验证失败，无法更新: " + e.getMessage(), e);
            }
        }
        
        strategyDO.setUpdatedAt(LocalDateTime.now());
        strategyMapper.updateById(strategyDO);
        return convertToDTO(strategyDO);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Boolean deleteStrategy(String id) {
        int result = strategyMapper.deleteById(id);
        return result > 0;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> regenerateStrategyCode(
            String strategyId,
            String strategyContext,
            String validateSymbol,
            String strategyName,
            Boolean persist) {
        StrategyDTO existing = getStrategyById(strategyId);
        if (existing == null) {
            throw new IllegalArgumentException("策略不存在: " + strategyId);
        }
        String type = existing.getType();
        if (type == null || type.trim().isEmpty()) {
            throw new IllegalArgumentException("策略类型为空，无法重新生成");
        }
        String context = StringUtils.hasText(strategyContext) ? strategyContext : existing.getStrategyContext();
        if (!StringUtils.hasText(context)) {
            throw new IllegalArgumentException("策略内容 strategy_context 为空：请在请求中传入 strategyContext 或在库中补全");
        }
        String typeNorm = type.trim().toLowerCase();
        String validateSym = null;
        if ("look".equals(typeNorm)) {
            validateSym = StringUtils.hasText(validateSymbol) ? validateSymbol.trim() : existing.getValidateSymbol();
            if (!StringUtils.hasText(validateSym)) {
                throw new IllegalArgumentException("盯盘策略须提供 validate_symbol（请求参数或库中已有）");
            }
        }

        String[] pm = resolveStrategyProviderAndModel();
        String generatedCode = aiProviderService.generateStrategyCode(
                pm[0], pm[1], context, typeNorm);

        String testName = StringUtils.hasText(strategyName) ? strategyName.trim()
                : (StringUtils.hasText(existing.getName()) ? existing.getName() : "策略");

        Map<String, Object> testResult;
        if ("look".equals(typeNorm)) {
            testResult = strategyCodeTesterService.testLookStrategyCode(generatedCode, testName, validateSym);
        } else {
            testResult = strategyCodeTesterService.testStrategyCode(generatedCode, typeNorm, testName);
        }
        boolean testPassed = Boolean.TRUE.equals(testResult.get("passed"));

        boolean doPersist = persist == null || Boolean.TRUE.equals(persist);

        Map<String, Object> response = new HashMap<>();
        response.put("id", strategyId);
        response.put("strategyCode", generatedCode);
        response.put("testPassed", testPassed);
        response.put("testResult", testResult);

        if (!doPersist) {
            response.put("persisted", false);
            response.put("message", "已生成代码与测试结果，未写入数据库（persist=false）");
            return response;
        }

        if (!testPassed) {
            response.put("persisted", false);
            response.put("message", "生成代码未通过测试，未写入数据库");
            return response;
        }

        StrategyDTO toUpdate = new StrategyDTO();
        BeanUtils.copyProperties(existing, toUpdate);
        toUpdate.setStrategyCode(generatedCode);
        if (StringUtils.hasText(strategyContext)) {
            toUpdate.setStrategyContext(strategyContext);
        }
        if (StringUtils.hasText(validateSymbol)) {
            toUpdate.setValidateSymbol(validateSymbol.trim());
        }
        updateStrategy(toUpdate);
        response.put("persisted", true);
        response.put("message", "策略代码已重新生成并通过测试，已保存");
        return response;
    }

    /**
     * 将DO转换为DTO
     * @param strategyDO 数据对象
     * @return 数据传输对象
     */
    private StrategyDTO convertToDTO(StrategyDO strategyDO) {
        StrategyDTO strategyDTO = new StrategyDTO();
        BeanUtils.copyProperties(strategyDO, strategyDTO);
        return strategyDTO;
    }

    /**
     * 将DTO转换为DO
     * @param strategyDTO 数据传输对象
     * @return 数据对象
     */
    private StrategyDO convertToDO(StrategyDTO strategyDTO) {
        StrategyDO strategyDO = new StrategyDO();
        BeanUtils.copyProperties(strategyDTO, strategyDO);
        return strategyDO;
    }

}

